from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError

from neural_grid_signal.http_client import urlopen_with_retries
from neural_grid_signal.models import CandidateStats, GridScoreResult, NotificationResult, StrategyDocument


def _action_text(score: GridScoreResult) -> str:
    if score.hard_blocked or score.direction == "wait":
        return "等待：硬风控或趋势风险未通过，不建议导入执行"
    if score.direction == "neutral_defensive":
        return "防守观察：可小资金观察，导入前人工确认区间仍有效"
    if score.final_score >= 75:
        return "可导入：按低杠杆网格执行，若突破区间及时暂停"
    return "人工复核：评分未到强推荐，确认风险后再导入"


def _number_text(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")


def format_telegram_message(
    strategy: StrategyDocument,
    score: GridScoreResult,
    strategy_path: str,
    *,
    stats: CandidateStats | None = None,
) -> str:
    grid = strategy.config["grid_config"]
    risks = ", ".join(score.risk_tags) if score.risk_tags else "none"
    reasons = "；".join(score.reasons[:3]) if score.reasons else "无"
    preflight = score.nofx_preflight
    bounds_mode = "ATR Auto Bounds" if grid.get("use_atr_bounds") else "Explicit Bounds"
    scan_lines = []
    if stats is not None:
        scan_lines = [
            "",
            "🔎 Scan Pool",
            f"• Total OKX Symbols: {stats.total_symbols}",
            f"• Liquidity Passed: {stats.liquidity_pass_count}",
            f"• Liquidity Filtered Out: {stats.liquidity_filtered_out_count}",
            f"• Grid Screening Pool: {stats.scoring_pool_count}",
            f"• Hard Filter Passed: {stats.hard_filter_pass_count}",
        ]
    return "\n".join(
        [
            f"🔥 AI Grid Signal | {score.symbol}",
            "━━━━━━━━━━━━━━━━━━━━",
            *scan_lines,
            "",
            "📊 Score",
            f"• Final: {score.final_score:.1f}",
            f"• Confidence: {score.confidence:.1f}",
            f"• Direction: {score.direction}",
            "",
            "🧭 Action",
            f"• {_action_text(score)}",
            "",
            "⚙️ Grid Setup",
            f"• Grid Count: {grid['grid_count']}",
            f"• Investment: {_number_text(grid['total_investment'])} USDT",
            f"• Leverage: {grid['leverage']}x",
            f"• Distribution: {grid['distribution']}",
            f"• Bias Ratio: {grid['direction_bias_ratio']}",
            f"• ATR Multiplier: {grid['atr_multiplier']}",
            f"• Stop Loss: {grid['stop_loss_pct']}%",
            f"• Daily Loss Limit: {grid['daily_loss_limit_pct']}%",
            f"• Bounds Mode: {bounds_mode}",
            f"• Range: {score.grid_lower_price:.8g} - {score.grid_upper_price:.8g}",
            "",
            "🧩 NOFX Preflight",
            f"• Verdict: {preflight.verdict.upper()}",
            f"• 5m BOLL Width: {preflight.bollinger_width_5m:.2f}%",
            f"• 4h Change: {preflight.price_change_4h:.2f}%",
            f"• BOLL Position: {preflight.bollinger_position_label}",
            f"• Grid Spacing: {preflight.grid_spacing:.8g}",
            f"• Spacing Display OK: {preflight.display_spacing_ok}",
            "",
            "🧪 Backtest",
            f"• Score: {score.backtest.score:.1f}",
            f"• Grid Hits: {score.backtest.grid_hits}",
            f"• Profit Proxy: {score.backtest.realized_profit_proxy}",
            f"• Max Drawdown: {score.backtest.max_drawdown_pct:.2f}%",
            f"• Inventory Skew: {score.backtest.inventory_skew_abs:.2f}",
            "",
            "🛡 Risk",
            f"• Tags: {risks}",
            f"• Reason: {reasons}",
            "",
            "📁 Strategy",
            f"• {strategy_path}",
        ]
    )


def _format_time(value: datetime | str | None) -> str:
    if value is None:
        return "none"
    if isinstance(value, datetime):
        zone = value.tzname() or ""
        return f"{value:%Y-%m-%d %H:%M:%S} {zone}".strip()
    return value


def format_scheduler_event_message(
    *,
    event: str,
    schedule_times: tuple[str, ...],
    timezone_name: str,
    next_run_at: datetime | str | None = None,
    pid: int | None = None,
    reason: str = "",
) -> str:
    event_key = event.upper()
    icon = {
        "STARTED": "🚦",
        "STOPPED": "🛑",
        "ERROR": "🚨",
    }.get(event_key, "ℹ️")
    lines = [
        f"{icon} NeuralGridSignal | {event_key}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"• Timezone: {timezone_name}",
        f"• Schedule: {' / '.join(schedule_times)}",
    ]
    if next_run_at is not None:
        lines.append(f"• Next Run: {_format_time(next_run_at)}")
    if pid is not None:
        lines.append(f"• PID: {pid}")
    if reason:
        lines.append(f"• Reason: {reason}")
    return "\n".join(lines)


@dataclass
class TelegramNotifier:
    bot_token: str
    channel_id: str
    dry_run: bool = False
    timeout_seconds: int = 12
    retry_attempts: int = 3
    retry_base_delay_seconds: float = 0.5

    async def send_strategy_signal(
        self,
        strategy: StrategyDocument,
        score: GridScoreResult,
        strategy_path: str,
        stats: CandidateStats | None = None,
    ) -> NotificationResult:
        message = format_telegram_message(strategy, score, strategy_path, stats=stats)
        return await self.send_text(message)

    async def send_scheduler_event(
        self,
        *,
        event: str,
        schedule_times: tuple[str, ...],
        timezone_name: str,
        next_run_at: datetime | str | None = None,
        pid: int | None = None,
        reason: str = "",
    ) -> NotificationResult:
        message = format_scheduler_event_message(
            event=event,
            schedule_times=schedule_times,
            timezone_name=timezone_name,
            next_run_at=next_run_at,
            pid=pid,
            reason=reason,
        )
        return await self.send_text(message)

    async def send_text(self, message: str) -> NotificationResult:
        if not self.bot_token or not self.channel_id:
            return NotificationResult(sent=False, reason="missing_credentials")
        if self.dry_run:
            return NotificationResult(sent=False, reason="dry_run", response={"text": message})
        return await asyncio.to_thread(self._send_message, message)

    def _send_message(self, text: str) -> NotificationResult:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.channel_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode()
        request = urllib.request.Request(url, data=payload, method="POST")
        try:
            with urlopen_with_retries(
                request,
                timeout=self.timeout_seconds,
                attempts=self.retry_attempts,
                base_delay_seconds=self.retry_base_delay_seconds,
            ) as response:
                body = response.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return NotificationResult(sent=bool(data.get("ok", True)), reason="sent", response=data)
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            detail = body or str(exc)
            try:
                parsed = json.loads(body) if body else {}
                detail = parsed.get("description") or detail
            except Exception:
                pass
            return NotificationResult(sent=False, reason=f"error:{exc.code}:{detail}")
        except Exception as exc:
            return NotificationResult(sent=False, reason=f"error:{exc}")
