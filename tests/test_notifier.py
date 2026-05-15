import asyncio
import io
from urllib.error import URLError
from urllib.error import HTTPError

from neural_grid_signal.models import BacktestResult, CandidateStats, GridScoreResult, NofxPreflight
from neural_grid_signal.notifier import TelegramNotifier, format_scheduler_event_message, format_telegram_message
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
        grid_lower_price=95,
        grid_upper_price=105,
        nofx_preflight=NofxPreflight(
            verdict="pass",
            bollinger_width_5m=2.4,
            price_change_4h=1.2,
            bollinger_position_label="middle",
            grid_spacing=1.25,
            display_spacing_ok=True,
        ),
    )
    return build_strategy_document(score), score


def test_format_telegram_message_contains_mobile_action_fields():
    strategy, score = _strategy_and_score()
    stats = CandidateStats(total_symbols=120, liquidity_pass_count=60, scoring_pool_count=40, hard_filter_pass_count=20)
    message = format_telegram_message(strategy, score, "output/strategies/demo.json", stats=stats)

    assert "SOLUSDT" in message
    assert "83.4" in message
    assert "Grid Setup" in message
    assert "ATR Multiplier" in message
    assert "Action" in message
    assert "Scan Pool" in message
    assert "120" in message
    assert "Liquidity Filtered Out" in message
    assert "60" in message
    assert "500 USDT" in message
    assert "NOFX Preflight" in message
    assert "Daily Trend" in message
    assert "PASS" in message
    assert "Range Width" in message
    assert "Explicit Bounds" in message
    assert "output/strategies/demo.json" in message


def test_format_scheduler_event_message_contains_schedule_context():
    message = format_scheduler_event_message(
        event="started",
        schedule_times=("08:00", "20:00"),
        timezone_name="Asia/Shanghai",
        next_run_at="2026-05-14 08:00 CST",
        pid=1234,
    )

    assert "STARTED" in message
    assert "08:00 / 20:00" in message
    assert "Asia/Shanghai" in message
    assert "2026-05-14 08:00 CST" in message
    assert "1234" in message


def test_telegram_notifier_skips_when_missing_credentials():
    strategy, score = _strategy_and_score()
    notifier = TelegramNotifier(bot_token="", channel_id="")

    result = asyncio.run(notifier.send_strategy_signal(strategy, score, "demo.json"))

    assert result.sent is False
    assert result.reason == "missing_credentials"


def test_telegram_notifier_send_text_returns_dry_run_message():
    notifier = TelegramNotifier(bot_token="token", channel_id="channel", dry_run=True)

    result = asyncio.run(notifier.send_text("service started"))

    assert result.sent is False
    assert result.reason == "dry_run"
    assert result.response == {"text": "service started"}


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


def test_telegram_notifier_retries_transient_send_error(monkeypatch):
    notifier = TelegramNotifier(bot_token="token", channel_id="channel")
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary failure")
        return FakeTelegramResponse({"ok": True})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    result = notifier._send_message("demo")

    assert result.sent is True
    assert calls == 2


class FakeTelegramResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return __import__("json").dumps(self.payload).encode("utf-8")
