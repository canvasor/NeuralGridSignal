from neural_grid_signal.backtest import simulate_grid
from neural_grid_signal.models import Candle


def _candles(closes):
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        rows.append(
            Candle(
                open_time=idx,
                open=previous,
                high=max(previous, close) + 0.8,
                low=min(previous, close) - 0.8,
                close=close,
                volume=1000,
                quote_volume=100_000,
            )
        )
    return rows


def test_grid_backtest_prefers_repeated_range_crossings():
    ranging = _candles([100, 102, 98, 103, 97, 102, 99, 101, 98, 103, 100, 102])
    trending = _candles([100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122])

    ranging_result = simulate_grid(ranging, grid_count=6, atr_multiplier=2.4, investment=200)
    trending_result = simulate_grid(trending, grid_count=6, atr_multiplier=2.4, investment=200)

    assert ranging_result.grid_hits > trending_result.grid_hits
    assert ranging_result.inventory_skew_abs < trending_result.inventory_skew_abs
    assert ranging_result.score > trending_result.score


def test_grid_backtest_rejects_insufficient_data():
    result = simulate_grid(_candles([100, 101]), grid_count=6, atr_multiplier=2.4, investment=200)

    assert result.score == 0
    assert "insufficient_data" in result.tags


def test_grid_backtest_uses_atr_multiplier_to_size_bounds():
    candles = _candles([100, 104, 98, 103, 97, 105, 99, 104, 98, 106, 100, 105])

    narrow = simulate_grid(candles, grid_count=8, atr_multiplier=1.2, investment=200)
    wide = simulate_grid(candles, grid_count=8, atr_multiplier=3.0, investment=200)

    assert narrow.grid_hits != wide.grid_hits
