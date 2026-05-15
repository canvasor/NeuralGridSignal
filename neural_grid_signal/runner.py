from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from neural_grid_signal.config import Settings, load_settings
from neural_grid_signal.market_data import CombinedMarketDataProvider
from neural_grid_signal.models import CandidateStats, GridScoreResult, NotificationResult, RunResult, StrategyDocument, SymbolMarketData
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
                investment=self.settings.grid_investment_usdt,
            )
        )

    async def run_once(self, limit: int | None = None) -> RunResult:
        rows: list[SymbolMarketData] = await self.market_data_provider.fetch_candidates(limit or self.settings.candidate_limit)
        if not rows:
            raise RuntimeError("no market data candidates fetched")
        scores = self.scorer.rank(rows)
        pass_candidates = [score for score in scores if not score.hard_blocked and score.nofx_preflight.verdict == "pass"]
        stats = self._candidate_stats()
        stats.scoring_pool_count = len(rows)
        stats.hard_filter_pass_count = len(pass_candidates)
        selected = pass_candidates[0] if pass_candidates else scores[0]
        outcome = "signal" if pass_candidates else "no_signal"
        logger.info("selected %s score=%.2f direction=%s outcome=%s", selected.symbol, selected.final_score, selected.direction, outcome)
        strategy = build_strategy_document(selected, investment=self.settings.grid_investment_usdt) if pass_candidates else None
        strategy_path, report_path, snapshot_path = self._write_outputs(strategy, selected, scores, stats, outcome)
        notification = await self._send_notification(strategy, selected, strategy_path, report_path, snapshot_path, stats)
        return RunResult(
            outcome=outcome,
            selected=selected,
            strategy=strategy,
            strategy_path=strategy_path,
            report_path=report_path,
            snapshot_path=snapshot_path,
            notification=notification,
            all_scores=scores,
            candidate_stats=stats,
        )

    def _candidate_stats(self) -> CandidateStats:
        stats = getattr(self.market_data_provider, "last_stats", None)
        return stats if isinstance(stats, CandidateStats) else CandidateStats()

    def _write_outputs(
        self,
        strategy: StrategyDocument | None,
        selected: GridScoreResult,
        scores: list[GridScoreResult],
        stats: CandidateStats,
        outcome: str,
    ) -> tuple[Path | None, Path, Path]:
        now = datetime.now(self.settings.timezone)
        stamp = now.strftime("%Y%m%d_%H%M%S_%f")
        strategy_dir = self.settings.output_dir / "strategies"
        report_dir = self.settings.output_dir / "reports"
        run_dir = self.settings.output_dir / "runs"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        symbol = selected.symbol.upper()
        strategy_path = strategy_dir / f"{stamp}_{symbol}_grid_signal.json" if strategy is not None else None
        report_path = report_dir / f"{stamp}_{symbol}_grid_signal.md"
        snapshot_path = run_dir / f"{stamp}_{symbol}_run_snapshot.json"
        if strategy_path is not None and strategy is not None:
            strategy_path.write_text(json.dumps(strategy.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.write_text(self._render_report(strategy, selected, scores, stats, outcome), encoding="utf-8")
        snapshot_path.write_text(
            json.dumps(self._render_snapshot(strategy, selected, scores, stats, outcome), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("wrote strategy=%s report=%s snapshot=%s", strategy_path, report_path, snapshot_path)
        return strategy_path, report_path, snapshot_path

    async def _send_notification(
        self,
        strategy: StrategyDocument | None,
        selected: GridScoreResult,
        strategy_path: Path | None,
        report_path: Path,
        snapshot_path: Path,
        stats: CandidateStats,
    ) -> NotificationResult | None:
        if strategy is None or strategy_path is None:
            send_no_signal = getattr(self.notifier, "send_no_signal", None)
            if callable(send_no_signal):
                result = await send_no_signal(selected, str(report_path), str(snapshot_path), stats=stats)
                return result if isinstance(result, NotificationResult) or result is None else None
            return None
        result = await self.notifier.send_strategy_signal(strategy, selected, str(strategy_path), stats=stats)
        return result if isinstance(result, NotificationResult) or result is None else None

    @staticmethod
    def _render_report(
        strategy: StrategyDocument | None,
        selected: GridScoreResult,
        scores: list[GridScoreResult],
        stats: CandidateStats,
        outcome: str,
    ) -> str:
        grid = strategy.config["grid_config"] if strategy is not None else None
        preflight = selected.nofx_preflight
        daily = selected.daily_trend
        bounds_mode = "none" if grid is None else "atr_auto" if grid.get("use_atr_bounds") else "explicit"
        lines = [
            f"# {selected.symbol} AI 网格信号",
            "",
            "## Scan Pool",
            "",
            f"- total_symbols: {stats.total_symbols}",
            f"- liquidity_pass_count: {stats.liquidity_pass_count}",
            f"- liquidity_filtered_out_count: {stats.liquidity_filtered_out_count}",
            f"- scoring_pool_count: {stats.scoring_pool_count}",
            f"- hard_filter_pass_count: {stats.hard_filter_pass_count}",
            f"- min_contract_volume_24h: {stats.min_contract_volume_24h}",
            "",
            "## Selection",
            "",
            f"- outcome: {outcome}",
            f"- final_score: {selected.final_score}",
            f"- confidence: {selected.confidence}",
            f"- direction: {selected.direction}",
            f"- atr_pct: {selected.atr_pct}",
            f"- range_efficiency: {selected.range_efficiency}",
            f"- grid_count: {grid['grid_count'] if grid else 0}",
            f"- atr_multiplier: {grid['atr_multiplier'] if grid else 0}",
            f"- total_investment: {grid['total_investment'] if grid else 0}",
            f"- bounds_mode: {bounds_mode}",
            f"- lower_price: {selected.grid_lower_price}",
            f"- upper_price: {selected.grid_upper_price}",
            f"- distribution: {grid['distribution'] if grid else 'none'}",
            f"- direction_bias_ratio: {grid['direction_bias_ratio'] if grid else 0}",
            f"- risk_tags: {', '.join(selected.risk_tags)}",
            f"- backtest_profit_proxy: {selected.backtest.realized_profit_proxy}",
            f"- backtest_max_drawdown_pct: {selected.backtest.max_drawdown_pct}",
            "",
            "## Daily Trend",
            "",
            f"- source: {daily.source}",
            f"- verdict: {daily.verdict}",
            f"- change_7d: {daily.change_7d}",
            f"- change_14d: {daily.change_14d}",
            f"- change_30d: {daily.change_30d}",
            f"- ema20_slope_pct: {daily.ema20_slope_pct}",
            f"- close_vs_ema20_pct: {daily.close_vs_ema20_pct}",
            f"- close_vs_ema50_pct: {daily.close_vs_ema50_pct}",
            f"- range_position_30d: {daily.range_position_30d}",
            f"- risk_tags: {', '.join(daily.risk_tags)}",
            "",
            "## NOFX Preflight",
            "",
            f"- source: {preflight.source}",
            f"- verdict: {preflight.verdict}",
            f"- bollinger_width_5m: {preflight.bollinger_width_5m}",
            f"- atr_pct_5m: {preflight.atr_pct_5m}",
            f"- rsi_5m: {preflight.rsi_5m}",
            f"- price_change_1h: {preflight.price_change_1h}",
            f"- price_change_4h: {preflight.price_change_4h}",
            f"- bollinger_position: {preflight.bollinger_position}",
            f"- bollinger_position_label: {preflight.bollinger_position_label}",
            f"- grid_range_pct: {preflight.grid_range_pct}",
            f"- grid_spacing: {preflight.grid_spacing}",
            f"- grid_spacing_pct: {preflight.grid_spacing_pct}",
            f"- display_spacing_ok: {preflight.display_spacing_ok}",
            f"- risk_tags: {', '.join(preflight.risk_tags)}",
            "",
            "## Reasons",
            "",
        ]
        lines.extend(f"- {reason}" for reason in selected.reasons)
        lines.extend(["", "## Top Candidates", ""])
        for item in scores[:10]:
            lines.append(f"- {item.symbol}: {item.final_score:.1f}, {item.direction}, risks={','.join(item.risk_tags)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_snapshot(
        strategy: StrategyDocument | None,
        selected: GridScoreResult,
        scores: list[GridScoreResult],
        stats: CandidateStats,
        outcome: str,
    ) -> dict[str, object]:
        return {
            "outcome": outcome,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "selected": {
                "symbol": selected.symbol,
                "final_score": selected.final_score,
                "confidence": selected.confidence,
                "direction": selected.direction,
                "risk_tags": selected.risk_tags,
                "reasons": selected.reasons,
                "nofx_preflight": {
                    "source": selected.nofx_preflight.source,
                    "verdict": selected.nofx_preflight.verdict,
                    "bollinger_width_5m": selected.nofx_preflight.bollinger_width_5m,
                    "price_change_4h": selected.nofx_preflight.price_change_4h,
                    "grid_range_pct": selected.nofx_preflight.grid_range_pct,
                    "grid_spacing": selected.nofx_preflight.grid_spacing,
                    "display_spacing_ok": selected.nofx_preflight.display_spacing_ok,
                    "risk_tags": selected.nofx_preflight.risk_tags,
                },
                "daily_trend": {
                    "source": selected.daily_trend.source,
                    "verdict": selected.daily_trend.verdict,
                    "change_7d": selected.daily_trend.change_7d,
                    "change_14d": selected.daily_trend.change_14d,
                    "change_30d": selected.daily_trend.change_30d,
                    "ema20_slope_pct": selected.daily_trend.ema20_slope_pct,
                    "close_vs_ema20_pct": selected.daily_trend.close_vs_ema20_pct,
                    "range_position_30d": selected.daily_trend.range_position_30d,
                    "risk_tags": selected.daily_trend.risk_tags,
                },
                "backtest": {
                    "score": selected.backtest.score,
                    "grid_hits": selected.backtest.grid_hits,
                    "profit_proxy": selected.backtest.realized_profit_proxy,
                    "max_drawdown_pct": selected.backtest.max_drawdown_pct,
                },
            },
            "candidate_stats": {
                "total_symbols": stats.total_symbols,
                "liquidity_pass_count": stats.liquidity_pass_count,
                "scoring_pool_count": stats.scoring_pool_count,
                "hard_filter_pass_count": stats.hard_filter_pass_count,
                "min_contract_volume_24h": stats.min_contract_volume_24h,
            },
            "strategy": strategy.to_dict() if strategy is not None else None,
            "top_candidates": [
                {
                    "symbol": item.symbol,
                    "final_score": item.final_score,
                    "direction": item.direction,
                    "hard_blocked": item.hard_blocked,
                    "risk_tags": item.risk_tags,
                    "nofx_preflight_verdict": item.nofx_preflight.verdict,
                }
                for item in scores[:10]
            ],
        }
