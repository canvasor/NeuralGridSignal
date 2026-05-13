from datetime import datetime
from zoneinfo import ZoneInfo

from neural_grid_signal.config import load_settings, parse_schedule_times
from neural_grid_signal.scheduler import next_run_after


def test_load_settings_uses_expected_environment_names():
    settings = load_settings(
        {
            "OKX_API_KEY_READONLY": "okx-key",
            "BINANCE_API_KEY_READONLY": "binance-key",
            "TELEGRAM_BOT_TOKEN_GRID": "tg-token",
            "TELEGRAM_CHANNEL_ID_GRID": "tg-channel",
            "OPEN_AI_ENDPOINT": "https://example.test/v1/chat/completions",
            "OPEN_AI_MODEL": "model",
            "OPEN_AI_API_KEY": "openai-key",
            "GRID_SIGNAL_SCHEDULE_TIMES": "08:00,20:00",
        }
    )

    assert settings.okx_api_key == "okx-key"
    assert settings.binance_api_key == "binance-key"
    assert settings.telegram_bot_token == "tg-token"
    assert settings.openai_model == "model"
    assert settings.schedule_times == ("08:00", "20:00")


def test_parse_schedule_times_rejects_bad_values():
    assert parse_schedule_times("8:00,20:00") == ("08:00", "20:00")
    assert parse_schedule_times("bad,25:99,09:30") == ("09:30",)


def test_next_run_after_uses_beijing_timezone():
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 5, 13, 20, 1, tzinfo=tz)

    result = next_run_after(now, ("08:00", "20:00"), tz)

    assert result == datetime(2026, 5, 14, 8, 0, tzinfo=tz)


def test_load_settings_reads_project_dotenv_when_environment_missing(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "TELEGRAM_BOT_TOKEN_GRID=token-from-dotenv\n"
        "TELEGRAM_CHANNEL_ID_GRID=channel-from-dotenv\n"
        "GRID_SIGNAL_SCHEDULE_TIMES=09:00,21:30\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN_GRID", raising=False)
    monkeypatch.delenv("TELEGRAM_CHANNEL_ID_GRID", raising=False)

    settings = load_settings()

    assert settings.telegram_bot_token == "token-from-dotenv"
    assert settings.telegram_channel_id == "channel-from-dotenv"
    assert settings.schedule_times == ("09:00", "21:30")
