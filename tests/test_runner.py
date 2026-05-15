import json
import asyncio

from neural_grid_signal.models import (
    CandidateStats,
    Candle,
    FundingSnapshot,
    OpenInterestSnapshot,
    OrderBookSnapshot,
    SymbolMarketData,
    TickerSnapshot,
)
from neural_grid_signal.runner import GridSignalRunner
from neural_grid_signal.config import Settings


def _candles(closes):
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        rows.append(Candle(idx, previous, max(previous, close) + 1, min(previous, close) - 1, close, 1000, 100_000))
    return rows


def _tight_candles(closes, wick=0.15):
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        rows.append(Candle(idx, previous, max(previous, close) + wick, min(previous, close) - wick, close, 1000, 100_000))
    return rows


class FakeMarketDataProvider:
    last_stats = CandidateStats(total_symbols=3, liquidity_pass_count=2, scoring_pool_count=1)

    async def fetch_candidates(self, limit):
        closes = [100, 102, 99, 101, 98, 102, 100, 101, 99, 102, 100, 101]
        return [
            SymbolMarketData(
                symbol="SOLUSDT",
                okx_ticker=TickerSnapshot("SOLUSDT", 101, 1.0, 80_000_000, 103, 98),
                okx_candles_5m=_tight_candles([100, 100.15, 99.95, 100.1, 99.98, 100.06, 100.0, 100.08, 99.99, 100.04] * 5),
                okx_candles_15m=_candles(closes),
                okx_candles_1h=_candles(closes[::2]),
                okx_candles_4h=_candles(closes[::4]),
                okx_funding=FundingSnapshot("SOLUSDT", 0.00004),
                okx_oi=OpenInterestSnapshot("SOLUSDT", 30_000_000, 0.5),
                okx_orderbook=OrderBookSnapshot("SOLUSDT", 100.98, 101.02),
            )
        ]

    async def close(self):
        return None


class FakeNoSignalMarketDataProvider:
    last_stats = CandidateStats(total_symbols=2, liquidity_pass_count=2, scoring_pool_count=2)

    async def fetch_candidates(self, limit):
        trending_5m = [
            0.386,
            0.389,
            0.391,
            0.388,
            0.392,
            0.394,
            0.391,
            0.395,
            0.397,
            0.394,
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
            0.46,
            0.463,
            0.459,
            0.465,
            0.468,
            0.471,
            0.467,
        ]
        flat = [0.39, 0.405, 0.385, 0.41, 0.39, 0.415, 0.395, 0.42, 0.4, 0.425, 0.405, 0.41]
        return [
            SymbolMarketData(
                symbol="ONDOUSDT",
                okx_ticker=TickerSnapshot("ONDOUSDT", 0.41, 4.0, 80_000_000, 0.43, 0.38),
                okx_candles_5m=_candles(trending_5m),
                okx_candles_15m=_candles(flat),
                okx_candles_1h=_candles(flat[::2]),
                okx_candles_4h=_candles(flat[::4]),
                okx_funding=FundingSnapshot("ONDOUSDT", 0.00004),
                okx_oi=OpenInterestSnapshot("ONDOUSDT", 30_000_000, 0.5),
                okx_orderbook=OrderBookSnapshot("ONDOUSDT", 0.4098, 0.4102),
            ),
            SymbolMarketData(
                symbol="PEPEUSDT",
                okx_ticker=TickerSnapshot("PEPEUSDT", 0.000012, 1.0, 90_000_000, 0.000013, 0.000011),
                okx_candles_5m=_candles([0.0000118, 0.0000121, 0.0000119, 0.0000122] * 13),
                okx_candles_15m=_candles([0.0000118, 0.0000121, 0.0000119, 0.0000122] * 6),
                okx_candles_1h=_candles([0.0000118, 0.0000121, 0.0000119, 0.0000122] * 3),
                okx_candles_4h=_candles([0.0000118, 0.0000121, 0.0000119, 0.0000122]),
                okx_funding=FundingSnapshot("PEPEUSDT", 0.00004),
                okx_oi=OpenInterestSnapshot("PEPEUSDT", 35_000_000, 0.4),
                okx_orderbook=OrderBookSnapshot("PEPEUSDT", 0.00001199, 0.00001201),
            ),
        ]

    async def close(self):
        return None


class FakeNotifier:
    def __init__(self):
        self.calls = []
        self.no_signal_calls = []

    async def send_strategy_signal(self, strategy, score, strategy_path, stats=None):
        self.calls.append((strategy, score, strategy_path, stats))
        return None

    async def send_no_signal(self, score, report_path, snapshot_path, stats=None):
        self.no_signal_calls.append((score, report_path, snapshot_path, stats))
        return None


def test_runner_generates_strategy_file_and_report(tmp_path):
    settings = Settings(output_dir=tmp_path, dry_run=True, grid_investment_usdt=750)
    notifier = FakeNotifier()
    runner = GridSignalRunner(settings=settings, market_data_provider=FakeMarketDataProvider(), notifier=notifier)

    result = asyncio.run(runner.run_once(limit=5))

    assert result.selected.symbol == "SOLUSDT"
    assert result.strategy_path.exists()
    assert result.report_path.exists()
    assert notifier.calls
    payload = json.loads(result.strategy_path.read_text(encoding="utf-8"))
    assert payload["config"]["grid_config"]["symbol"] == "SOLUSDT"
    assert payload["config"]["grid_config"]["total_investment"] == 750
    report = result.report_path.read_text(encoding="utf-8")
    assert "## NOFX Preflight" in report
    assert "## Daily Trend" in report
    assert "bounds_mode: explicit" in report
    assert result.snapshot_path.exists()
    assert result.candidate_stats.scoring_pool_count == 1
    assert notifier.calls[0][3].total_symbols == 3


def test_runner_output_paths_do_not_collide_within_same_minute(tmp_path):
    settings = Settings(output_dir=tmp_path, dry_run=True)
    runner = GridSignalRunner(settings=settings, market_data_provider=FakeMarketDataProvider(), notifier=FakeNotifier())
    result_a = asyncio.run(runner.run_once(limit=5))
    result_b = asyncio.run(runner.run_once(limit=5))

    assert result_a.strategy_path != result_b.strategy_path


def test_runner_emits_no_signal_when_no_prefight_pass_candidate(tmp_path):
    settings = Settings(output_dir=tmp_path, dry_run=True, grid_investment_usdt=500)
    notifier = FakeNotifier()
    runner = GridSignalRunner(settings=settings, market_data_provider=FakeNoSignalMarketDataProvider(), notifier=notifier)

    result = asyncio.run(runner.run_once(limit=5))

    assert result.outcome == "no_signal"
    assert result.strategy is None
    assert result.strategy_path is None
    assert result.snapshot_path.exists()
    assert notifier.calls == []
    assert notifier.no_signal_calls
    report = result.report_path.read_text(encoding="utf-8")
    assert "no_signal" in report
