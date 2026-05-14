from neural_grid_signal.models import (
    Candle,
    FundingSnapshot,
    OpenInterestSnapshot,
    OrderBookSnapshot,
    SymbolMarketData,
    TickerSnapshot,
)
from neural_grid_signal.scoring import GridScorer, ScoringConfig


def _candles(symbol, closes):
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        rows.append(
            Candle(
                open_time=idx,
                open=previous,
                high=max(previous, close) + 1,
                low=min(previous, close) - 1,
                close=close,
                volume=1000,
                quote_volume=100_000,
            )
        )
    return rows


def _tight_candles(symbol, closes, wick_pct=0.002):
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        high = max(previous, close) * (1 + wick_pct)
        low = min(previous, close) * (1 - wick_pct)
        rows.append(
            Candle(
                open_time=idx,
                open=previous,
                high=high,
                low=low,
                close=close,
                volume=1000,
                quote_volume=100_000,
            )
        )
    return rows


def _market(symbol, closes, volume=80_000_000, oi=30_000_000, funding=0.00005, okx_5m_closes=None):
    price = closes[-1]
    return SymbolMarketData(
        symbol=symbol,
        okx_ticker=TickerSnapshot(
            symbol=symbol,
            price=price,
            price_change_24h=(price - closes[-5]) / closes[-5] * 100,
            volume_24h=volume,
            high_24h=max(closes[-5:]),
            low_24h=min(closes[-5:]),
        ),
        okx_candles_5m=_tight_candles(symbol, okx_5m_closes) if okx_5m_closes else [],
        okx_candles_15m=_candles(symbol, closes),
        okx_candles_1h=_candles(symbol, closes[::2] or closes),
        okx_candles_4h=_candles(symbol, closes[::4] or closes),
        okx_funding=FundingSnapshot(symbol=symbol, funding_rate=funding),
        okx_oi=OpenInterestSnapshot(symbol=symbol, oi_value=oi, oi_change_1h=1.0),
        okx_orderbook=OrderBookSnapshot(symbol=symbol, best_bid=price * 0.9998, best_ask=price * 1.0002),
        binance_ticker=TickerSnapshot(
            symbol=symbol,
            price=price * 1.0001,
            price_change_24h=(price - closes[-5]) / closes[-5] * 100,
            volume_24h=volume * 1.5,
            high_24h=max(closes[-5:]),
            low_24h=min(closes[-5:]),
        ),
        binance_candles_15m=_candles(symbol, closes),
        binance_funding=FundingSnapshot(symbol=symbol, funding_rate=funding * 0.9),
        binance_oi=OpenInterestSnapshot(symbol=symbol, oi_value=oi * 1.2, oi_change_1h=0.8),
    )


def test_scorer_prefers_ranging_market_over_single_direction_market():
    scorer = GridScorer(ScoringConfig(min_volume_24h=10_000_000, min_oi_value=10_000_000))
    ranging = _market("RANGEUSDT", [100, 102, 99, 101, 98, 102, 99, 101, 98, 102, 100, 101])
    trending = _market("TRENDUSDT", [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122])

    ranging_score = scorer.score(ranging)
    trending_score = scorer.score(trending)

    assert ranging_score.final_score > trending_score.final_score
    assert not ranging_score.hard_blocked
    assert "trend_risk" in trending_score.risk_tags


def test_scorer_hard_blocks_low_liquidity_and_extreme_funding():
    scorer = GridScorer(ScoringConfig(min_volume_24h=10_000_000, min_oi_value=10_000_000))
    weak = _market("WEAKUSDT", [100, 101, 99, 100, 101, 99, 100, 101], volume=1_000_000, oi=1_000_000, funding=0.001)

    result = scorer.score(weak)

    assert result.hard_blocked
    assert "low_volume" in result.risk_tags
    assert "low_oi" in result.risk_tags
    assert "extreme_funding" in result.risk_tags


def test_scorer_caps_confidence_for_neutral_defensive():
    scorer = GridScorer(ScoringConfig(min_volume_24h=10_000_000, min_oi_value=10_000_000))
    market = _market("DEFUSDT", [110, 108, 106, 109, 105, 108, 104, 107, 103, 106, 102, 104])

    result = scorer.score(market)

    assert result.direction == "neutral_defensive"
    assert result.confidence <= 84


def test_scorer_penalizes_slow_downtrend_despite_range_crossings():
    scorer = GridScorer(ScoringConfig(min_volume_24h=10_000_000, min_oi_value=10_000_000, investment=500))
    choppy = _market("DOGEUSDT", [100, 104, 98, 105, 97, 104, 99, 105, 98, 104, 100, 105])
    slow_downtrend = _market("CLUSDT", [110, 111, 108, 109, 106, 107, 104, 105, 102, 103, 100, 101])

    choppy_score = scorer.score(choppy)
    downtrend_score = scorer.score(slow_downtrend)

    assert "trend_risk" in downtrend_score.risk_tags
    assert choppy_score.final_score > downtrend_score.final_score


def test_scorer_uses_optimized_backtest_parameters():
    scorer = GridScorer(ScoringConfig(min_volume_24h=10_000_000, min_oi_value=10_000_000, investment=500))
    result = scorer.score(_market("RANGEUSDT", [100, 102, 98, 103, 97, 102, 99, 101, 98, 103, 100, 102]))

    assert result.recommended_grid_count >= 6
    assert result.recommended_atr_multiplier >= 2.0
    assert result.grid_lower_price > 0
    assert result.grid_upper_price > result.grid_lower_price


def test_scorer_rejects_nofx_runtime_trend_conditions():
    scorer = GridScorer(ScoringConfig(min_volume_24h=10_000_000, min_oi_value=10_000_000, investment=500))
    base_5m = [0.386, 0.389, 0.391, 0.388, 0.392, 0.394, 0.391, 0.395, 0.397, 0.394]
    trend_5m = base_5m + [
        0.396,
        0.399,
        0.402,
        0.398,
        0.404,
        0.407,
        0.409,
        0.406,
        0.411,
        0.414,
        0.416,
        0.413,
        0.418,
        0.421,
        0.424,
        0.419,
        0.425,
        0.428,
        0.431,
        0.427,
        0.433,
        0.436,
        0.439,
        0.435,
        0.441,
        0.444,
        0.447,
        0.443,
        0.449,
        0.452,
        0.455,
        0.451,
        0.457,
        0.460,
        0.463,
        0.459,
        0.465,
        0.468,
        0.471,
        0.467,
        0.473,
        0.476,
        0.479,
        0.475,
        0.481,
        0.484,
        0.487,
        0.483,
        0.489,
        0.492,
    ]
    market = _market(
        "ONDOUSDT",
        [0.39, 0.405, 0.385, 0.41, 0.39, 0.415, 0.395, 0.42, 0.4, 0.425, 0.405, 0.41],
        okx_5m_closes=trend_5m,
    )

    result = scorer.score(market)

    assert result.nofx_preflight.verdict == "reject"
    assert result.hard_blocked
    assert "nofx_runtime_reject" in result.risk_tags
    assert "wide_5m_bollinger" in result.risk_tags
    assert "strong_4h_move" in result.risk_tags
    assert result.final_score <= 39


def test_scorer_prefers_binance_5m_for_nofx_preflight():
    scorer = GridScorer(ScoringConfig(min_volume_24h=10_000_000, min_oi_value=10_000_000, investment=500))
    market = _market(
        "SOLUSDT",
        [100, 102, 99, 101, 98, 102, 100, 101, 99, 102, 100, 102],
        okx_5m_closes=[
            100,
            101,
            102,
            101,
            103,
            104,
            105,
            104,
            106,
            107,
            108,
            107,
            109,
            110,
            111,
            110,
            112,
            113,
            114,
            113,
            115,
            116,
            117,
            116,
            118,
            119,
            120,
            119,
            121,
            122,
            123,
            122,
            124,
            125,
            126,
            125,
            127,
            128,
            129,
            128,
            130,
            131,
            132,
            131,
            133,
            134,
            135,
            134,
            136,
            137,
        ],
    )
    market.binance_candles_5m = _tight_candles(
        "SOLUSDT",
        [100, 100.5, 99.8, 100.7, 100.2, 100.9, 100.1, 101.0, 100.4, 101.1] * 5,
        wick_pct=0.001,
    )

    result = scorer.score(market)

    assert result.nofx_preflight.source == "binance_5m"
    assert result.nofx_preflight.verdict != "reject"
