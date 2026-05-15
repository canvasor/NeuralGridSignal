from neural_grid_signal.backtest import grid_bounds, optimize_grid, simulate_grid
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


def test_grid_bounds_match_nofx_atr_bounds_formula():
    candles = _candles([100, 101, 100, 100])

    lower, upper = grid_bounds(candles, atr_multiplier=2.0, bound_atr=4.0)

    assert lower == 92
    assert upper == 108


def test_grid_backtest_records_selected_range_parameters():
    candles = _candles([100, 102, 98, 103, 97, 102, 99, 101, 98, 103, 100, 102])

    result = simulate_grid(candles, grid_count=8, atr_multiplier=2.5, investment=500, bound_atr=3.0)

    assert result.grid_count == 8
    assert result.atr_multiplier == 2.5
    assert result.lower_price > 0
    assert result.upper_price > result.lower_price


def test_optimize_grid_returns_best_grid_parameters():
    candles = _candles([100, 102, 98, 103, 97, 102, 99, 101, 98, 103, 100, 102])

    result = optimize_grid(candles, investment=500, bound_atr=3.0, grid_counts=(6, 8), atr_multipliers=(2.0, 2.6))

    assert result.grid_count in {6, 8}
    assert result.atr_multiplier in {2.0, 2.6}
    assert result.score > 0


def test_optimize_grid_skips_ranges_above_max_range_pct():
    candles = _candles([100, 102, 98, 103, 97, 102, 99, 101, 98, 103, 100, 102])

    result = optimize_grid(
        candles,
        investment=500,
        bound_atr=3.0,
        max_range_pct=12.0,
        grid_counts=(6,),
        atr_multipliers=(2.0, 3.0),
    )

    assert result.atr_multiplier == 2.0
    assert (result.upper_price - result.lower_price) / candles[-1].close * 100 <= 12.0


def test_optimize_grid_marks_all_candidates_too_wide():
    candles = _candles([100, 102, 98, 103, 97, 102, 99, 101, 98, 103, 100, 102])

    result = optimize_grid(
        candles,
        investment=500,
        bound_atr=6.5,
        max_range_pct=12.0,
        grid_counts=(6,),
        atr_multipliers=(2.0,),
    )

    assert result.score == 0
    assert "grid_range_too_wide" in result.tags


def test_grid_backtest_counts_intrabar_crossings_from_high_low_path():
    candles = [
        Candle(open_time=0, open=100, high=100.5, low=99.5, close=100, volume=1000, quote_volume=100_000),
        Candle(open_time=1, open=100, high=103.2, low=96.8, close=100, volume=1000, quote_volume=100_000),
        Candle(open_time=2, open=100, high=100.4, low=99.6, close=100, volume=1000, quote_volume=100_000),
        Candle(open_time=3, open=100, high=100.4, low=99.6, close=100, volume=1000, quote_volume=100_000),
        Candle(open_time=4, open=100, high=100.4, low=99.6, close=100, volume=1000, quote_volume=100_000),
        Candle(open_time=5, open=100, high=100.4, low=99.6, close=100, volume=1000, quote_volume=100_000),
    ]

    result = simulate_grid(candles, grid_count=5, atr_multiplier=1.0, investment=200, bound_atr=2.0)

    assert result.grid_hits > 0
