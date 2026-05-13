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
    okx_funding: FundingSnapshot | None = None
    okx_oi: OpenInterestSnapshot | None = None
    okx_orderbook: OrderBookSnapshot | None = None
    binance_ticker: TickerSnapshot | None = None
    binance_candles_15m: list[Candle] = field(default_factory=list)
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
    strategy: StrategyDocument
    strategy_path: Path
    report_path: Path
    notification: NotificationResult | None = None
    all_scores: list[GridScoreResult] = field(default_factory=list)
