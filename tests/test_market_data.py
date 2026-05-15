import asyncio

from neural_grid_signal.config import Settings
from neural_grid_signal.market_data import CombinedMarketDataProvider
from neural_grid_signal.models import Candle, FundingSnapshot, OpenInterestSnapshot, OrderBookSnapshot, TickerSnapshot


def _candles():
    closes = [100, 102, 99, 101, 98, 102, 100, 101, 99, 102, 100, 101] * 2
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        rows.append(Candle(idx, previous, max(previous, close) + 1, min(previous, close) - 1, close, 1000, 100_000))
    return rows


class FakeOKX:
    def __init__(self):
        self.kline_calls = []

    async def get_all_tickers(self):
        return {
            "SOLUSDT": TickerSnapshot("SOLUSDT", 101, 1.0, 80_000_000, 103, 98),
            "DOGEUSDT": TickerSnapshot("DOGEUSDT", 0.2, 1.0, 45_000_000, 0.22, 0.18),
            "THINUSDT": TickerSnapshot("THINUSDT", 1.0, 1.0, 5_000_000, 1.1, 0.9),
        }

    async def get_klines(self, symbol, interval="15m", limit=192):
        self.kline_calls.append((symbol, interval, limit))
        return _candles()

    async def get_funding_rate(self, symbol):
        return FundingSnapshot(symbol, 0.00004)

    async def get_open_interest(self, symbol, price=0):
        return OpenInterestSnapshot(symbol, 30_000_000, 0.5)

    async def get_orderbook(self, symbol, depth=20):
        return OrderBookSnapshot(symbol, 100.98, 101.02)

    async def close(self):
        return None


class FakeBinance:
    def __init__(self):
        self.kline_calls = []

    async def get_all_tickers(self):
        return {
            "SOLUSDT": TickerSnapshot("SOLUSDT", 101, 1.0, 120_000_000, 103, 98),
            "DOGEUSDT": TickerSnapshot("DOGEUSDT", 0.2, 1.0, 80_000_000, 0.22, 0.18),
        }

    async def get_all_funding_rates(self):
        return {}

    async def get_klines(self, symbol, interval="15m", limit=192):
        self.kline_calls.append((symbol, interval, limit))
        return _candles()

    async def get_open_interest(self, symbol, price=0):
        return OpenInterestSnapshot(symbol, 40_000_000, 0.7)

    async def close(self):
        return None


def test_market_data_provider_records_candidate_stats():
    provider = CombinedMarketDataProvider(Settings(min_contract_volume_24h=40_000_000))
    provider.okx = FakeOKX()
    provider.binance = FakeBinance()

    rows = asyncio.run(provider.fetch_candidates(limit=10))

    assert [row.symbol for row in rows] == ["SOLUSDT", "DOGEUSDT"]
    assert rows[0].okx_candles_5m
    assert rows[0].okx_candles_1d
    assert rows[0].binance_candles_5m
    assert rows[0].binance_candles_1d
    assert ("SOLUSDT", "5m", 50) in provider.okx.kline_calls
    assert ("SOLUSDT", "1d", 60) in provider.okx.kline_calls
    assert ("SOLUSDT", "5m", 50) in provider.binance.kline_calls
    assert ("SOLUSDT", "1d", 60) in provider.binance.kline_calls
    assert provider.last_stats.total_symbols == 3
    assert provider.last_stats.liquidity_pass_count == 2
    assert provider.last_stats.scoring_pool_count == 2
    assert provider.last_stats.min_contract_volume_24h == 40_000_000
