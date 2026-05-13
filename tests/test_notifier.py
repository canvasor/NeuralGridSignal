import asyncio
import io
from urllib.error import HTTPError

from neural_grid_signal.models import BacktestResult, GridScoreResult
from neural_grid_signal.notifier import TelegramNotifier, format_telegram_message
from neural_grid_signal.strategy import build_strategy_document


def _strategy_and_score():
    score = GridScoreResult(
        symbol="SOLUSDT",
        final_score=83.4,
        confidence=80,
        direction="long_bias",
        atr_pct=2.2,
        range_efficiency=0.25,
        risk_tags=["near_range_middle"],
        reasons=["震荡质量高"],
        breakdown={"range": 25},
        backtest=BacktestResult(score=74, grid_hits=16, realized_profit_proxy=3.0, inventory_skew_abs=0.1),
    )
    return build_strategy_document(score), score


def test_format_telegram_message_contains_mobile_action_fields():
    strategy, score = _strategy_and_score()
    message = format_telegram_message(strategy, score, "output/strategies/demo.json")

    assert "SOLUSDT" in message
    assert "83.4" in message
    assert "grid_count" in message
    assert "atr_multiplier" in message
    assert "action:" in message
    assert "output/strategies/demo.json" in message


def test_telegram_notifier_skips_when_missing_credentials():
    strategy, score = _strategy_and_score()
    notifier = TelegramNotifier(bot_token="", channel_id="")

    result = asyncio.run(notifier.send_strategy_signal(strategy, score, "demo.json"))

    assert result.sent is False
    assert result.reason == "missing_credentials"


def test_telegram_notifier_includes_telegram_error_body(monkeypatch):
    strategy, score = _strategy_and_score()
    notifier = TelegramNotifier(bot_token="token", channel_id="bad-channel")

    def fake_urlopen(_request, timeout):
        raise HTTPError(
            url="https://api.telegram.org/botTOKEN/sendMessage",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=io.BytesIO(b'{"ok":false,"description":"Bad Request: chat not found"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = asyncio.run(notifier.send_strategy_signal(strategy, score, "demo.json"))

    assert result.sent is False
    assert "chat not found" in result.reason
