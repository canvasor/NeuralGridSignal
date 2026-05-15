from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    quote_volume: float = 0.0
    close_time: int = 0


@dataclass(frozen=True)
class TickerSnapshot:
    symbol: str
    price: float
    price_change_24h: float
    volume_24h: float
    high_24h: float
    low_24h: float


@dataclass(frozen=True)
class FundingSnapshot:
    symbol: str
    funding_rate: float
    next_funding_time: int = 0


@dataclass(frozen=True)
class OpenInterestSnapshot:
    symbol: str
    oi_value: float
    oi_change_1h: float = 0.0
    oi_delta_value_1h: float = 0.0


@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    best_bid: float
    best_ask: float
    bid_notional: float = 0.0
    ask_notional: float = 0.0

    @property
    def spread_bps(self) -> float:
        mid = (self.best_bid + self.best_ask) / 2
        if mid <= 0:
            return 9999.0
        return (self.best_ask - self.best_bid) / mid * 10_000


@dataclass
class SymbolMarketData:
    symbol: str
    okx_ticker: TickerSnapshot
    okx_candles_15m: list[Candle]
    okx_candles_1h: list[Candle]
    okx_candles_4h: list[Candle] = field(default_factory=list)
    okx_candles_5m: list[Candle] = field(default_factory=list)
    okx_candles_1d: list[Candle] = field(default_factory=list)
    okx_funding: FundingSnapshot | None = None
    okx_oi: OpenInterestSnapshot | None = None
    okx_orderbook: OrderBookSnapshot | None = None
    binance_ticker: TickerSnapshot | None = None
    binance_candles_5m: list[Candle] = field(default_factory=list)
    binance_candles_15m: list[Candle] = field(default_factory=list)
    binance_candles_1d: list[Candle] = field(default_factory=list)
    binance_funding: FundingSnapshot | None = None
    binance_oi: OpenInterestSnapshot | None = None


@dataclass
class BacktestResult:
    score: float = 0.0
    grid_hits: int = 0
    realized_profit_proxy: float = 0.0
    inventory_skew_abs: float = 0.0
    max_drawdown_pct: float = 0.0
    tags: list[str] = field(default_factory=list)
    grid_count: int = 0
    atr_multiplier: float = 0.0
    lower_price: float = 0.0
    upper_price: float = 0.0


@dataclass
class NofxPreflight:
    source: str = "unknown"
    verdict: str = "unknown"
    bollinger_width_5m: float = 0.0
    atr_pct_5m: float = 0.0
    rsi_5m: float = 50.0
    price_change_1h: float = 0.0
    price_change_4h: float = 0.0
    bollinger_position: float = 0.5
    bollinger_position_label: str = "middle"
    grid_range_pct: float = 0.0
    grid_spacing: float = 0.0
    grid_spacing_pct: float = 0.0
    display_spacing_ok: bool = True
    risk_tags: list[str] = field(default_factory=list)


@dataclass
class DailyTrend:
    source: str = "unknown"
    verdict: str = "unknown"
    change_7d: float = 0.0
    change_14d: float = 0.0
    change_30d: float = 0.0
    ema20_slope_pct: float = 0.0
    close_vs_ema20_pct: float = 0.0
    close_vs_ema50_pct: float = 0.0
    range_position_30d: float = 0.5
    risk_tags: list[str] = field(default_factory=list)


@dataclass
class GridScoreResult:
    symbol: str
    final_score: float
    confidence: float
    direction: str
    atr_pct: float
    range_efficiency: float
    risk_tags: list[str]
    reasons: list[str]
    breakdown: dict[str, float]
    backtest: BacktestResult
    hard_blocked: bool = False
    recommended_grid_count: int = 8
    recommended_atr_multiplier: float = 2.4
    grid_lower_price: float = 0.0
    grid_upper_price: float = 0.0
    nofx_preflight: NofxPreflight = field(default_factory=NofxPreflight)
    daily_trend: DailyTrend = field(default_factory=DailyTrend)


@dataclass
class CandidateStats:
    total_symbols: int = 0
    liquidity_pass_count: int = 0
    scoring_pool_count: int = 0
    hard_filter_pass_count: int = 0
    min_contract_volume_24h: float = 0.0

    @property
    def liquidity_filtered_out_count(self) -> int:
        return max(0, self.total_symbols - self.liquidity_pass_count)


@dataclass
class StrategyDocument:
    name: str
    description: str
    config: dict[str, Any]
    exported_at: str
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "config": self.config,
            "exported_at": self.exported_at,
            "version": self.version,
        }


@dataclass
class NotificationResult:
    sent: bool
    reason: str = ""
    response: dict[str, Any] | None = None


@dataclass
class RunResult:
    selected: GridScoreResult
    strategy: StrategyDocument | None
    strategy_path: Path | None
    report_path: Path
    outcome: str = "signal"
    snapshot_path: Path = field(default_factory=Path)
    notification: NotificationResult | None = None
    all_scores: list[GridScoreResult] = field(default_factory=list)
    candidate_stats: CandidateStats = field(default_factory=CandidateStats)
