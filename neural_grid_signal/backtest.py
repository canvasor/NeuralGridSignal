from __future__ import annotations

from neural_grid_signal.indicators import atr, atr_percent, max_drawdown_percent
from neural_grid_signal.models import BacktestResult, Candle


def grid_bounds(candles: list[Candle], atr_multiplier: float, bound_atr: float | None = None) -> tuple[float, float]:
    if not candles:
        return 0.0, 0.0
    current_price = candles[-1].close
    if current_price <= 0:
        return 0.0, 0.0
    atr_value = bound_atr if bound_atr is not None and bound_atr > 0 else atr(candles)
    half_range = atr_value * max(0.1, atr_multiplier)
    if half_range <= 0:
        return 0.0, 0.0
    return max(0.0, current_price - half_range), current_price + half_range


def _levels(candles: list[Candle], grid_count: int, atr_multiplier: float, bound_atr: float | None = None) -> list[float]:
    if grid_count < 2:
        return []
    low, high = grid_bounds(candles, atr_multiplier, bound_atr)
    if low <= 0 or high <= low:
        return []
    spacing = (high - low) / (grid_count - 1)
    return [low + spacing * idx for idx in range(grid_count)]


def _crossed_levels(levels: list[float], start: float, end: float) -> list[float]:
    if start == end:
        return []
    if end > start:
        return [level for level in levels if start < level <= end]
    return list(reversed([level for level in levels if end <= level < start]))


def _path_points(candle: Candle) -> tuple[float, ...]:
    if candle.close > candle.open:
        return (candle.open, candle.low, candle.high, candle.close)
    if candle.close < candle.open:
        return (candle.open, candle.high, candle.low, candle.close)
    upper_wick = candle.high - candle.open
    lower_wick = candle.open - candle.low
    if lower_wick > upper_wick:
        return (candle.open, candle.low, candle.high, candle.close)
    return (candle.open, candle.high, candle.low, candle.close)


def simulate_grid(
    candles: list[Candle],
    grid_count: int,
    atr_multiplier: float,
    investment: float,
    fee_bps: float = 4.0,
    bound_atr: float | None = None,
) -> BacktestResult:
    if len(candles) < max(6, grid_count):
        return BacktestResult(score=0.0, tags=["insufficient_data"])

    levels = _levels(candles, grid_count, atr_multiplier, bound_atr)
    if not levels:
        return BacktestResult(score=0.0, tags=["invalid_range"])

    spacing = (levels[-1] - levels[0]) / max(1, grid_count - 1)
    center = (levels[-1] + levels[0]) / 2
    if center <= 0 or spacing <= 0:
        return BacktestResult(score=0.0, tags=["invalid_range"])

    inventory = 0
    max_inventory = 0
    grid_hits = 0
    realized_profit = 0.0
    unit_notional = investment / grid_count
    fee_cost = fee_bps / 10_000 * unit_notional

    for candle in candles[1:]:
        path = _path_points(candle)
        for start, end in zip(path, path[1:]):
            crossed = _crossed_levels(levels, start, end)
            for _level in crossed:
                grid_hits += 1
                previous_inventory = inventory
                if end > start:
                    inventory -= 1
                else:
                    inventory += 1
                if previous_inventory and (
                    previous_inventory > 0 > inventory
                    or previous_inventory < 0 < inventory
                    or abs(inventory) < abs(previous_inventory)
                ):
                    realized_profit += max(0.0, spacing / center * unit_notional - fee_cost * 2)
                max_inventory = max(max_inventory, abs(inventory))

    hit_score = min(40.0, grid_hits * 3.0)
    profit_score = min(20.0, realized_profit / max(1.0, investment) * 500.0)
    skew = max_inventory / max(1, grid_count)
    skew_penalty = min(30.0, skew * 35.0)
    drawdown = max_drawdown_percent(candles)
    drawdown_penalty = min(20.0, drawdown * 1.2)
    atr_pct = atr_percent(candles)
    atr_penalty = 0.0
    if atr_pct <= 0.35:
        atr_penalty = 20.0
    elif atr_pct > 8:
        atr_penalty = min(30.0, (atr_pct - 8) * 4)

    score = max(0.0, min(100.0, 45.0 + hit_score + profit_score - skew_penalty - drawdown_penalty - atr_penalty))
    tags: list[str] = []
    if skew > 0.65:
        tags.append("inventory_skew")
    if grid_hits < grid_count:
        tags.append("low_grid_activity")
    if drawdown > 12:
        tags.append("large_drawdown")

    return BacktestResult(
        score=round(score, 2),
        grid_hits=grid_hits,
        realized_profit_proxy=round(realized_profit, 4),
        inventory_skew_abs=round(abs(inventory) / max(1, grid_count), 4),
        max_drawdown_pct=drawdown,
        tags=tags,
        grid_count=grid_count,
        atr_multiplier=atr_multiplier,
        lower_price=round(levels[0], 8),
        upper_price=round(levels[-1], 8),
    )


def optimize_grid(
    candles: list[Candle],
    *,
    investment: float,
    bound_atr: float | None = None,
    min_spacing: float = 0.0,
    grid_counts: tuple[int, ...] = (6, 7, 8, 9, 10, 11, 12),
    atr_multipliers: tuple[float, ...] = (2.0, 2.2, 2.4, 2.6, 2.8, 3.0),
) -> BacktestResult:
    best = BacktestResult(score=0.0, tags=["no_grid_candidate"])
    for grid_count in grid_counts:
        for multiplier in atr_multipliers:
            result = simulate_grid(candles, grid_count, multiplier, investment, bound_atr=bound_atr)
            if min_spacing > 0 and result.grid_count > 1:
                spacing = (result.upper_price - result.lower_price) / (result.grid_count - 1)
                if spacing < min_spacing:
                    continue
            if result.score > best.score:
                best = result
    return best
