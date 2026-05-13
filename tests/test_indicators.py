from neural_grid_signal.indicators import (
    atr_percent,
    bollinger_width_percent,
    ema_slope_percent,
    max_drawdown_percent,
    range_efficiency,
    rsi,
)
from neural_grid_signal.models import Candle


def _candles(closes):
    rows = []
    for idx, close in enumerate(closes):
        prev = closes[idx - 1] if idx else close
        high = max(prev, close) + 1
        low = min(prev, close) - 1
        rows.append(
            Candle(
                open_time=idx,
                open=prev,
                high=high,
                low=low,
                close=close,
                volume=1000,
                quote_volume=100_000,
            )
        )
    return rows


def test_range_efficiency_distinguishes_trend_from_chop():
    choppy = _candles([100, 102, 99, 101, 98, 102, 100, 101])
    trending = _candles([100, 102, 104, 106, 108, 110, 112, 114])

    assert range_efficiency(choppy) < 0.35
    assert range_efficiency(trending) > 0.85


def test_atr_and_bollinger_width_are_percent_values():
    candles = _candles([100, 101, 99, 102, 98, 103, 100, 104, 99, 105, 101, 106, 102, 107, 103])

    assert 2.0 < atr_percent(candles, period=14) < 8.0
    assert bollinger_width_percent(candles, period=10) > 0


def test_ema_slope_rsi_and_drawdown_are_stable():
    candles = _candles([100, 101, 102, 103, 104, 105, 106, 107])

    assert ema_slope_percent(candles, period=4, lookback=3) > 0
    assert rsi(candles, period=6) > 70
    assert max_drawdown_percent(_candles([100, 104, 102, 98, 101])) == 5.769230769230769
