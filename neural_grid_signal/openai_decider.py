from __future__ import annotations

import asyncio
import json
import urllib.request
from dataclasses import dataclass
from typing import Any

from neural_grid_signal.config import Settings
from neural_grid_signal.models import GridScoreResult


@dataclass
class OpenAIDecision:
    enabled: bool
    recommendation: str = "skip"
    reason: str = ""
    raw: dict[str, Any] | None = None


class OpenAIGridDecider:
    def __init__(self, settings: Settings, timeout_seconds: int = 20):
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self.settings.openai_endpoint and self.settings.openai_model and self.settings.openai_api_key)

    async def review(self, scores: list[GridScoreResult]) -> OpenAIDecision:
        if not self.enabled:
            return OpenAIDecision(enabled=False, reason="missing_openai_config")
        payload = self._payload(scores[:8])
        return await asyncio.to_thread(self._post, payload)

    def _payload(self, scores: list[GridScoreResult]) -> dict[str, Any]:
        compact = [
            {
                "symbol": item.symbol,
                "score": item.final_score,
                "direction": item.direction,
                "atr_pct": item.atr_pct,
                "range_efficiency": item.range_efficiency,
                "risk_tags": item.risk_tags,
                "backtest": {
                    "score": item.backtest.score,
                    "hits": item.backtest.grid_hits,
                    "skew": item.backtest.inventory_skew_abs,
                },
            }
            for item in scores
        ]
        return {
            "model": self.settings.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是网格策略风控复核器。只基于给定数据，返回最适合低风险网格的币种和一句风险理由。",
                },
                {
                    "role": "user",
                    "content": json.dumps({"candidates": compact}, ensure_ascii=False),
                },
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

    def _post(self, payload: dict[str, Any]) -> OpenAIDecision:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.settings.openai_endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.openai_api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            parsed = json.loads(content)
            return OpenAIDecision(
                enabled=True,
                recommendation=str(parsed.get("symbol") or parsed.get("recommendation") or ""),
                reason=str(parsed.get("reason") or ""),
                raw=data,
            )
        except Exception as exc:
            return OpenAIDecision(enabled=True, recommendation="skip", reason=f"openai_error:{exc}")
