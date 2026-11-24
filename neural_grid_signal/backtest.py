from __future__ import annotations

from neural_grid_signal.indicators import atr, atr_percent
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
    return (candle.open, candle.low, candle.high, candle.close)


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

    # Evaluation bounds use only a prefix; current 4h ATR is for deployment, not historical fills.
    warmup = min(14, max(1, len(candles) // 4))
    levels = _levels(candles[:warmup], grid_count, atr_multiplier)
    proposal = _levels(candles, grid_count, atr_multiplier, bound_atr)
    if not levels or not proposal:
        return BacktestResult(score=0.0, tags=["invalid_range"])

    spacing = (levels[-1] - levels[0]) / max(1, grid_count - 1)
    center = (levels[-1] + levels[0]) / 2
    if center <= 0 or spacing <= 0:
        return BacktestResult(score=0.0, tags=["invalid_range"])

    lots = []
    max_inventory = 0
    grid_hits = 0
    cash = investment
    unit_quantity = investment / grid_count / center
    peak = investment
    drawdown = 0.0

    def equity(mark):
        return cash + sum(side * unit_quantity * (mark - price) for _, side, price in lots)

    for candle in candles[warmup:]:
        path = _path_points(candle)
        for start, end in zip(path, path[1:]):
            for price in _crossed_levels(levels, start, end):
                side = -1 if end > start else 1
                if lots and lots[0][1] != side:
                    _, previous_side, entry = lots.pop(0)
                    cash += previous_side * unit_quantity * (price - entry)
                elif any(index == price for index, _, _ in lots) or len(lots) >= grid_count:
                    continue
                else:
                    lots.append((price, side, price))
                cash -= fee_bps / 10000 * unit_quantity * price
                grid_hits += 1
                max_inventory = max(max_inventory, len(lots))
                value = equity(price)
                peak = max(peak, value)
                drawdown = max(drawdown, (peak - value) / peak * 100)
            value = equity(end)
            peak = max(peak, value)
            drawdown = max(drawdown, (peak - value) / peak * 100)
    realized_profit = cash - investment
    net_profit = equity(candles[-1].close) - investment - len(lots) * unit_quantity * candles[-1].close * fee_bps / 10000
    hit_score = min(40.0, grid_hits * 3.0)
    profit_score = max(-40.0, min(20.0, net_profit / max(1.0, investment) * 500.0))
    skew = max_inventory / max(1, grid_count)
    skew_penalty = min(30.0, skew * 35.0)
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
        inventory_skew_abs=round(len(lots) / max(1, grid_count), 4),
        max_drawdown_pct=drawdown,
        tags=tags,
        grid_count=grid_count,
        atr_multiplier=atr_multiplier,
        lower_price=round(proposal[0], 8),
        upper_price=round(proposal[-1], 8),
        evaluation_lower_price=levels[0],
        evaluation_upper_price=levels[-1],
        net_equity_return_pct=net_profit / investment * 100,
    )


def optimize_grid(
    candles: list[Candle],
    *,
    investment: float,
    bound_atr: float | None = None,
    min_spacing: float = 0.0,
    max_range_pct: float = 0.0,
    grid_counts: tuple[int, ...] = (6, 7, 8, 9, 10, 11, 12),
    atr_multipliers: tuple[float, ...] = (2.0, 2.2, 2.4, 2.6, 2.8, 3.0),
) -> BacktestResult:
    best = BacktestResult(score=0.0, tags=["no_grid_candidate"])
    skipped_too_wide = 0
    current_price = candles[-1].close if candles else 0.0
    for grid_count in grid_counts:
        for multiplier in atr_multipliers:
            result = simulate_grid(candles, grid_count, multiplier, investment, bound_atr=bound_atr)
            if max_range_pct > 0 and current_price > 0 and result.upper_price > result.lower_price:
                range_pct = (result.upper_price - result.lower_price) / current_price * 100
                if range_pct > max_range_pct:
                    skipped_too_wide += 1
                    continue
            if min_spacing > 0 and result.grid_count > 1:
                spacing = (result.upper_price - result.lower_price) / (result.grid_count - 1)
                if spacing < min_spacing:
                    continue
            if result.score > best.score:
                best = result
    if best.score == 0 and skipped_too_wide:
        return BacktestResult(score=0.0, tags=["no_grid_candidate", "grid_range_too_wide"])
    return best
