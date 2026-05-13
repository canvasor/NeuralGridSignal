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


def _market(symbol, closes, volume=80_000_000, oi=30_000_000, funding=0.00005):
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
        okx_candles_15m=_candles(symbol, closes),
        okx_candles_1h=_candles(symbol, closes[::2] or closes),
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
