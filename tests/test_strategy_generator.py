import json
from datetime import datetime, timezone

from neural_grid_signal.models import BacktestResult, GridScoreResult
from neural_grid_signal.strategy import build_strategy_document


def _score(symbol="SOLUSDT", final_score=82, direction="long_bias", atr_pct=2.4):
    return GridScoreResult(
        symbol=symbol,
        final_score=final_score,
        confidence=78,
        direction=direction,
        atr_pct=atr_pct,
        range_efficiency=0.28,
        risk_tags=[],
        reasons=["震荡质量较好", "Binance 辅助确认"],
        breakdown={"range": 24, "risk": 18},
        backtest=BacktestResult(score=76, grid_hits=18, realized_profit_proxy=3.2, inventory_skew_abs=0.2),
        recommended_grid_count=9,
        recommended_atr_multiplier=2.6,
        grid_lower_price=95,
        grid_upper_price=105,
    )


def test_build_strategy_document_matches_nofx_grid_import_shape():
    document = build_strategy_document(_score(), exported_at=datetime(2026, 5, 13, tzinfo=timezone.utc))
    payload = document.to_dict()

    assert payload["config"]["strategy_type"] == "grid_trading"
    assert payload["config"]["coin_source"]["static_coins"] == ["SOLUSDT"]
    assert payload["config"]["grid_config"]["symbol"] == "SOLUSDT"
    assert payload["config"]["grid_config"]["distribution"] == "pyramid"
    assert 0.75 <= payload["config"]["grid_config"]["direction_bias_ratio"] <= 0.85
    assert payload["config"]["grid_config"]["leverage"] == 2
    assert payload["config"]["grid_config"]["total_investment"] == 500
    assert payload["config"]["grid_config"]["grid_count"] == 9
    assert payload["config"]["grid_config"]["atr_multiplier"] == 2.6
    assert "prompt_sections" in payload["config"]
    json.dumps(payload, ensure_ascii=False)


def test_build_strategy_document_uses_gaussian_for_neutral_light_long():
    payload = build_strategy_document(_score("ETHUSDT", direction="neutral_light_long", atr_pct=1.8)).to_dict()

    grid = payload["config"]["grid_config"]
    assert grid["distribution"] == "gaussian"
    assert 0.58 <= grid["direction_bias_ratio"] <= 0.68
    assert grid["grid_count"] >= 8


def test_build_strategy_document_marks_neutral_defensive_as_observation():
    payload = build_strategy_document(_score("ZECUSDT", direction="neutral_defensive", atr_pct=0.8)).to_dict()

    assert "防守观察" in payload["name"]
    assert "防守观察" in payload["config"]["prompt_sections"]["role_definition"]
    grid = payload["config"]["grid_config"]
    assert grid["total_investment"] == 500
    assert grid["atr_multiplier"] >= 2.35
    assert grid["direction_bias_ratio"] == 0.55


def test_build_strategy_document_accepts_investment_override():
    payload = build_strategy_document(_score(), investment=750).to_dict()

    assert payload["config"]["grid_config"]["total_investment"] == 750


def test_build_strategy_document_exports_explicit_bounds_for_nofx_container():
    payload = build_strategy_document(_score()).to_dict()

    grid = payload["config"]["grid_config"]
    assert grid["use_atr_bounds"] is False
    assert grid["lower_price"] == 95
    assert grid["upper_price"] == 105
