from pathlib import Path

from neural_grid_signal.__main__ import format_run_result
from neural_grid_signal.models import BacktestResult, GridScoreResult, NotificationResult, RunResult, StrategyDocument


def test_format_run_result_prints_notification_status():
    score = GridScoreResult(
        symbol="SOLUSDT",
        final_score=81.2,
        confidence=80,
        direction="long_bias",
        atr_pct=2.1,
        range_efficiency=0.2,
        risk_tags=[],
        reasons=[],
        breakdown={},
        backtest=BacktestResult(score=70),
    )
    result = RunResult(
        selected=score,
        strategy=StrategyDocument("demo", "demo", {"grid_config": {}}, "2026-05-13T00:00:00Z"),
        strategy_path=Path("output/strategies/demo.json"),
        report_path=Path("output/reports/demo.md"),
        notification=NotificationResult(sent=False, reason="missing_credentials"),
    )

    text = format_run_result(result)

    assert "notification=skipped reason=missing_credentials" in text
    assert "report=output/reports/demo.md" in text
