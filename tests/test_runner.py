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


class FakeMarketDataProvider:
    last_stats = CandidateStats(total_symbols=3, liquidity_pass_count=2, scoring_pool_count=1)

    async def fetch_candidates(self, limit):
        closes = [100, 102, 99, 101, 98, 102, 100, 101, 99, 102, 100, 101]
        return [
            SymbolMarketData(
                symbol="SOLUSDT",
                okx_ticker=TickerSnapshot("SOLUSDT", 101, 1.0, 80_000_000, 103, 98),
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


class FakeNotifier:
    def __init__(self):
        self.calls = []

    async def send_strategy_signal(self, strategy, score, strategy_path, stats=None):
        self.calls.append((strategy, score, strategy_path, stats))
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
    assert "bounds_mode: explicit" in report
    assert result.candidate_stats.scoring_pool_count == 1
    assert notifier.calls[0][3].total_symbols == 3


def test_runner_output_paths_do_not_collide_within_same_minute(tmp_path):
    settings = Settings(output_dir=tmp_path, dry_run=True)
    runner = GridSignalRunner(settings=settings, market_data_provider=FakeMarketDataProvider(), notifier=FakeNotifier())
    result_a = asyncio.run(runner.run_once(limit=5))
    result_b = asyncio.run(runner.run_once(limit=5))

    assert result_a.strategy_path != result_b.strategy_path
