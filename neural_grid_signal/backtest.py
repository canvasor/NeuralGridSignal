from __future__ import annotations

from neural_grid_signal.indicators import atr, atr_percent, max_drawdown_percent
from neural_grid_signal.models import BacktestResult, Candle


def _levels(candles: list[Candle], grid_count: int, atr_multiplier: float) -> list[float]:
    lows = [c.low for c in candles if c.low > 0]
    highs = [c.high for c in candles if c.high > 0]
    if not lows or not highs or grid_count < 2:
        return []
    current_price = candles[-1].close
    half_range = atr(candles) * max(0.1, atr_multiplier)
    if current_price <= 0 or half_range <= 0:
        return []
    low = max(0.0, current_price - half_range)
    high = current_price + half_range
    spacing = (high - low) / (grid_count - 1)
    return [low + spacing * idx for idx in range(grid_count)]


def simulate_grid(
    candles: list[Candle],
    grid_count: int,
    atr_multiplier: float,
    investment: float,
    fee_bps: float = 4.0,
) -> BacktestResult:
    if len(candles) < max(6, grid_count):
        return BacktestResult(score=0.0, tags=["insufficient_data"])

    levels = _levels(candles, grid_count, atr_multiplier)
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

    for prev, current in zip(candles, candles[1:]):
        start = prev.close
        end = current.close
        if start == end:
            continue
        low = min(start, end)
        high = max(start, end)
        crossed = [level for level in levels if low < level <= high]
        if not crossed:
            continue
        if end < start:
            crossed = list(reversed(crossed))

        for _level in crossed:
            grid_hits += 1
            previous_inventory = inventory
            if end > start:
                inventory -= 1
            else:
                inventory += 1
            if previous_inventory and (previous_inventory > 0 > inventory or previous_inventory < 0 < inventory or abs(inventory) < abs(previous_inventory)):
                realized_profit += max(0.0, spacing / center * unit_notional - fee_cost)
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
    )
