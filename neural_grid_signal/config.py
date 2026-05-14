from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo


def parse_schedule_times(value: str | None) -> tuple[str, ...]:
    raw = value or "08:00,20:00"
    result: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not re.fullmatch(r"\d{1,2}:\d{2}", item):
            continue
        hour_text, minute_text = item.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            result.append(f"{hour:02d}:{minute:02d}")
    return tuple(dict.fromkeys(result)) or ("08:00", "20:00")


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    try:
        return float(env.get(key, default))
    except (TypeError, ValueError):
        return default


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(env.get(key, default))
    except (TypeError, ValueError):
        return default


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


@dataclass
class Settings:
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_api_passphrase: str = ""
    binance_api_key: str = ""
    binance_api_secret: str = ""
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    openai_endpoint: str = ""
    openai_model: str = ""
    openai_api_key: str = ""
    schedule_times: tuple[str, ...] = ("08:00", "20:00")
    timezone_name: str = "Asia/Shanghai"
    output_dir: Path = field(default_factory=lambda: Path("output"))
    candidate_limit: int = 40
    min_volume_24h: float = 10_000_000
    min_contract_volume_24h: float = 10_000_000
    min_oi_value: float = 10_000_000
    grid_investment_usdt: float = 500
    dry_run: bool = False

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        source = _load_dotenv(Path(".env"))
        source.update(os.environ)
    else:
        source = dict(env)
    return Settings(
        okx_api_key=source.get("OKX_API_KEY_READONLY") or source.get("OKX_API_KEY", ""),
        okx_api_secret=source.get("OKX_API_SECRET_READONLY") or source.get("OKX_API_SECRET", ""),
        okx_api_passphrase=source.get("OKX_API_PASSPHRASE_READONLY") or source.get("OKX_API_PASSPHRASE", ""),
        binance_api_key=source.get("BINANCE_API_KEY_READONLY") or source.get("BINANCE_API_KEY", ""),
        binance_api_secret=source.get("BINANCE_API_SECRET_READONLY") or source.get("BINANCE_API_SECRET", ""),
        telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN_GRID", ""),
        telegram_channel_id=source.get("TELEGRAM_CHANNEL_ID_GRID", ""),
        openai_endpoint=source.get("OPEN_AI_ENDPOINT", ""),
        openai_model=source.get("OPEN_AI_MODEL", ""),
        openai_api_key=source.get("OPEN_AI_API_KEY", ""),
        schedule_times=parse_schedule_times(source.get("GRID_SIGNAL_SCHEDULE_TIMES")),
        timezone_name=source.get("GRID_SIGNAL_TIMEZONE", "Asia/Shanghai"),
        output_dir=Path(source.get("GRID_SIGNAL_OUTPUT_DIR", "output")),
        candidate_limit=_int(source, "GRID_SIGNAL_CANDIDATE_LIMIT", 40),
        min_volume_24h=_float(source, "GRID_SIGNAL_MIN_VOLUME_24H", 10_000_000),
        min_contract_volume_24h=_float(source, "GRID_SIGNAL_MIN_CONTRACT_VOLUME_24H", 10_000_000),
        min_oi_value=_float(source, "GRID_SIGNAL_MIN_OI_VALUE", 10_000_000),
        grid_investment_usdt=_float(source, "GRID_SIGNAL_INVESTMENT_USDT", 500),
        dry_run=source.get("GRID_SIGNAL_DRY_RUN", "").lower() in {"1", "true", "yes", "on"},
    )
