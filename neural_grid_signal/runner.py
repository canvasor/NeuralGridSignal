from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from neural_grid_signal.config import Settings, load_settings
from neural_grid_signal.market_data import CombinedMarketDataProvider
from neural_grid_signal.models import NotificationResult, RunResult, SymbolMarketData
from neural_grid_signal.notifier import TelegramNotifier
from neural_grid_signal.scoring import GridScorer, ScoringConfig
from neural_grid_signal.strategy import build_strategy_document

logger = logging.getLogger(__name__)


class GridSignalRunner:
    def __init__(
        self,
        settings: Settings | None = None,
        market_data_provider: object | None = None,
        notifier: object | None = None,
    ):
        self.settings = settings or load_settings()
        self.market_data_provider = market_data_provider or CombinedMarketDataProvider(self.settings)
        self.notifier = notifier or TelegramNotifier(
            bot_token=self.settings.telegram_bot_token,
            channel_id=self.settings.telegram_channel_id,
            dry_run=self.settings.dry_run,
        )
        self.scorer = GridScorer(
            ScoringConfig(
                min_volume_24h=self.settings.min_volume_24h,
                min_oi_value=self.settings.min_oi_value,
            )
        )

    async def run_once(self, limit: int | None = None) -> RunResult:
        rows: list[SymbolMarketData] = await self.market_data_provider.fetch_candidates(limit or self.settings.candidate_limit)
        if not rows:
            raise RuntimeError("no market data candidates fetched")
        scores = self.scorer.rank(rows)
        eligible = [score for score in scores if not score.hard_blocked]
        selected = eligible[0] if eligible else scores[0]
        logger.info("selected %s score=%.2f direction=%s", selected.symbol, selected.final_score, selected.direction)
        strategy = build_strategy_document(selected)
        strategy_path, report_path = self._write_outputs(strategy, selected, scores)
        notification = await self._send_notification(strategy, selected, str(strategy_path))
        return RunResult(
            selected=selected,
            strategy=strategy,
            strategy_path=strategy_path,
            report_path=report_path,
            notification=notification,
            all_scores=scores,
        )

    def _write_outputs(self, strategy, selected, scores) -> tuple[Path, Path]:
        now = datetime.now(self.settings.timezone)
        stamp = now.strftime("%Y%m%d_%H%M%S_%f")
        strategy_dir = self.settings.output_dir / "strategies"
        report_dir = self.settings.output_dir / "reports"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        symbol = selected.symbol.upper()
        strategy_path = strategy_dir / f"{stamp}_{symbol}_grid_signal.json"
        report_path = report_dir / f"{stamp}_{symbol}_grid_signal.md"
        strategy_path.write_text(json.dumps(strategy.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.write_text(self._render_report(strategy, selected, scores), encoding="utf-8")
        logger.info("wrote strategy=%s report=%s", strategy_path, report_path)
        return strategy_path, report_path

    async def _send_notification(self, strategy, selected, path: str) -> NotificationResult | None:
        result = await self.notifier.send_strategy_signal(strategy, selected, path)
        return result if isinstance(result, NotificationResult) or result is None else None

    @staticmethod
    def _render_report(strategy, selected, scores) -> str:
        grid = strategy.config["grid_config"]
        lines = [
            f"# {selected.symbol} AI 网格信号",
            "",
            f"- final_score: {selected.final_score}",
            f"- confidence: {selected.confidence}",
            f"- direction: {selected.direction}",
            f"- atr_pct: {selected.atr_pct}",
            f"- range_efficiency: {selected.range_efficiency}",
            f"- grid_count: {grid['grid_count']}",
            f"- atr_multiplier: {grid['atr_multiplier']}",
            f"- distribution: {grid['distribution']}",
            f"- direction_bias_ratio: {grid['direction_bias_ratio']}",
            f"- risk_tags: {', '.join(selected.risk_tags)}",
            "",
            "## Reasons",
            "",
        ]
        lines.extend(f"- {reason}" for reason in selected.reasons)
        lines.extend(["", "## Top Candidates", ""])
        for item in scores[:10]:
            lines.append(f"- {item.symbol}: {item.final_score:.1f}, {item.direction}, risks={','.join(item.risk_tags)}")
        return "\n".join(lines) + "\n"
