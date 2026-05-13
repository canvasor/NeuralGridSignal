from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from dataclasses import dataclass

from neural_grid_signal.models import GridScoreResult, NotificationResult, StrategyDocument


def _action_text(score: GridScoreResult) -> str:
    if score.hard_blocked or score.direction == "wait":
        return "等待：硬风控或趋势风险未通过，不建议导入执行"
    if score.direction == "neutral_defensive":
        return "防守观察：可小资金观察，导入前人工确认区间仍有效"
    if score.final_score >= 75:
        return "可导入：按低杠杆网格执行，若突破区间及时暂停"
    return "人工复核：评分未到强推荐，确认风险后再导入"


def format_telegram_message(strategy: StrategyDocument, score: GridScoreResult, strategy_path: str) -> str:
    grid = strategy.config["grid_config"]
    risks = ", ".join(score.risk_tags) if score.risk_tags else "none"
    reasons = "；".join(score.reasons[:3]) if score.reasons else "无"
    return (
        "AI网格信号\n"
        f"symbol: {score.symbol}\n"
        f"score: {score.final_score:.1f}, confidence: {score.confidence:.1f}, direction: {score.direction}\n"
        f"action: {_action_text(score)}\n"
        f"grid_count: {grid['grid_count']}, investment: {grid['total_investment']} USDT, leverage: {grid['leverage']}x\n"
        f"distribution: {grid['distribution']}, direction_bias_ratio: {grid['direction_bias_ratio']}\n"
        f"atr_multiplier: {grid['atr_multiplier']}, stop_loss_pct: {grid['stop_loss_pct']}, daily_loss_limit_pct: {grid['daily_loss_limit_pct']}\n"
        f"backtest: score {score.backtest.score:.1f}, hits {score.backtest.grid_hits}, skew {score.backtest.inventory_skew_abs:.2f}\n"
        f"risk_tags: {risks}\n"
        f"reason: {reasons}\n"
        f"strategy_file: {strategy_path}"
    )


@dataclass
class TelegramNotifier:
    bot_token: str
    channel_id: str
    dry_run: bool = False
    timeout_seconds: int = 12

    async def send_strategy_signal(
        self,
        strategy: StrategyDocument,
        score: GridScoreResult,
        strategy_path: str,
    ) -> NotificationResult:
        if not self.bot_token or not self.channel_id:
            return NotificationResult(sent=False, reason="missing_credentials")
        message = format_telegram_message(strategy, score, strategy_path)
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
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
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
