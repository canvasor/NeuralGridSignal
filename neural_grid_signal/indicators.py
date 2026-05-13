from __future__ import annotations

import math
import statistics

from neural_grid_signal.models import Candle


def _closes(candles: list[Candle]) -> list[float]:
    return [float(c.close) for c in candles if c.close > 0]


def true_ranges(candles: list[Candle]) -> list[float]:
    ranges: list[float] = []
    previous_close = None
    for candle in candles:
        if candle.high <= 0 or candle.low <= 0:
            continue
        if previous_close is None:
            ranges.append(candle.high - candle.low)
        else:
            ranges.append(
                max(
                    candle.high - candle.low,
                    abs(candle.high - previous_close),
                    abs(candle.low - previous_close),
                )
            )
        previous_close = candle.close
    return ranges


def atr(candles: list[Candle], period: int = 14) -> float:
    ranges = true_ranges(candles)
    if not ranges:
        return 0.0
    window = ranges[-period:] if len(ranges) >= period else ranges
    return statistics.fmean(window)


def atr_percent(candles: list[Candle], period: int = 14) -> float:
    closes = _closes(candles)
    if not closes:
        return 0.0
    return atr(candles, period=period) / closes[-1] * 100


def range_efficiency(candles: list[Candle]) -> float:
    closes = _closes(candles)
    if len(closes) < 2:
        return 0.0
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    if path <= 0:
        return 0.0
    return min(1.0, abs(closes[-1] - closes[0]) / path)


def bollinger_width_percent(candles: list[Candle], period: int = 20, stdevs: float = 2.0) -> float:
    closes = _closes(candles)
    if len(closes) < 2:
        return 0.0
    window = closes[-period:] if len(closes) >= period else closes
    middle = statistics.fmean(window)
    if middle <= 0:
        return 0.0
    sigma = statistics.pstdev(window)
    return (2 * stdevs * sigma) / middle * 100


def ema_values(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    if period <= 1:
        return values[:]
    alpha = 2 / (period + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append(alpha * value + (1 - alpha) * output[-1])
    return output


def ema_slope_percent(candles: list[Candle], period: int = 20, lookback: int = 5) -> float:
    closes = _closes(candles)
    if len(closes) <= lookback:
        return 0.0
    values = ema_values(closes, period)
    previous = values[-lookback - 1]
    if previous <= 0:
        return 0.0
    return (values[-1] - previous) / previous * 100


def rsi(candles: list[Candle], period: int = 14) -> float:
    closes = _closes(candles)
    if len(closes) < 2:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    window = deltas[-period:] if len(deltas) >= period else deltas
    gains = [max(delta, 0.0) for delta in window]
    losses = [abs(min(delta, 0.0)) for delta in window]
    avg_gain = statistics.fmean(gains) if gains else 0.0
    avg_loss = statistics.fmean(losses) if losses else 0.0
    if avg_loss <= 1e-12:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def max_drawdown_percent(candles: list[Candle]) -> float:
    closes = _closes(candles)
    if not closes:
        return 0.0
    peak = closes[0]
    max_dd = 0.0
    for close in closes:
        peak = max(peak, close)
        if peak > 0:
            max_dd = max(max_dd, (peak - close) / peak * 100)
    return max_dd


def close_position_in_range(candles: list[Candle]) -> float:
    closes = _closes(candles)
    if not closes:
        return 0.5
    lows = [c.low for c in candles if c.low > 0]
    highs = [c.high for c in candles if c.high > 0]
    if not lows or not highs:
        return 0.5
    low = min(lows)
    high = max(highs)
    if high <= low:
        return 0.5
    return min(1.0, max(0.0, (closes[-1] - low) / (high - low)))


def pct_change(first: float, last: float) -> float:
    if first <= 0:
        return 0.0
    return (last - first) / first * 100


def clamp(value: float, lower: float, upper: float) -> float:
    if math.isnan(value):
        return lower
    return max(lower, min(upper, value))
