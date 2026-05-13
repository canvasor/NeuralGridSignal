from __future__ import annotations

from dataclasses import dataclass

from neural_grid_signal.backtest import simulate_grid
from neural_grid_signal.indicators import (
    atr_percent,
    bollinger_width_percent,
    clamp,
    close_position_in_range,
    ema_slope_percent,
    pct_change,
    range_efficiency,
    rsi,
)
from neural_grid_signal.models import GridScoreResult, SymbolMarketData


@dataclass(frozen=True)
class ScoringConfig:
    min_volume_24h: float = 10_000_000
    min_oi_value: float = 10_000_000
    min_atr_pct: float = 0.35
    max_atr_pct: float = 8.0
    extreme_funding_abs: float = 0.0008
    max_abs_24h_change: float = 18.0


class GridScorer:
    def __init__(self, config: ScoringConfig | None = None):
        self.config = config or ScoringConfig()

    def score(self, data: SymbolMarketData) -> GridScoreResult:
        candles = data.okx_candles_15m
        long_candles = data.okx_candles_1h or candles
        ticker = data.okx_ticker
        funding = data.okx_funding.funding_rate if data.okx_funding else 0.0
        oi_value = data.okx_oi.oi_value if data.okx_oi else 0.0
        oi_change = data.okx_oi.oi_change_1h if data.okx_oi else 0.0

        atr_pct = atr_percent(candles)
        efficiency = range_efficiency(candles)
        boll_width = bollinger_width_percent(candles)
        slope = ema_slope_percent(long_candles, period=20, lookback=min(5, max(1, len(long_candles) // 4)))
        rsi_value = rsi(candles)
        position = close_position_in_range(candles)
        two_day_change = pct_change(candles[0].close, candles[-1].close) if candles else 0.0
        backtest = simulate_grid(candles, grid_count=8, atr_multiplier=2.4, investment=200)

        risk_tags: list[str] = []
        reasons: list[str] = []
        hard_blocked = False

        if ticker.volume_24h < self.config.min_volume_24h:
            risk_tags.append("low_volume")
            hard_blocked = True
        if oi_value < self.config.min_oi_value:
            risk_tags.append("low_oi")
            hard_blocked = True
        if atr_pct < self.config.min_atr_pct:
            risk_tags.append("too_low_volatility")
            hard_blocked = True
        if atr_pct > self.config.max_atr_pct:
            risk_tags.append("too_high_volatility")
            hard_blocked = True
        if abs(funding) > self.config.extreme_funding_abs:
            risk_tags.append("extreme_funding")
            hard_blocked = True
        if abs(ticker.price_change_24h) > self.config.max_abs_24h_change:
            risk_tags.append("large_24h_move")
        if efficiency > 0.72 or abs(two_day_change) > 14 or abs(slope) > 4:
            risk_tags.append("trend_risk")
        if position < 0.08 or position > 0.92:
            risk_tags.append("near_range_edge")
        else:
            risk_tags.append("near_range_middle")
        if abs(oi_change) > 12:
            risk_tags.append("oi_spike")

        liquidity_score = self._liquidity_score(ticker.volume_24h, oi_value, data.okx_orderbook.spread_bps if data.okx_orderbook else 8.0)
        volatility_score = self._volatility_score(atr_pct)
        range_score = self._range_score(efficiency, position, boll_width)
        funding_score = self._funding_score(funding)
        binance_score = self._binance_confirmation_score(data, two_day_change, atr_pct)
        risk_score = self._risk_score(risk_tags)

        final = (
            liquidity_score * 0.18
            + volatility_score * 0.16
            + range_score * 0.24
            + backtest.score * 0.22
            + funding_score * 0.08
            + binance_score * 0.06
            + risk_score * 0.06
        )
        if hard_blocked:
            final = min(final, 39.0)
        if "trend_risk" in risk_tags:
            final -= 14.0
        if "near_range_edge" in risk_tags:
            final -= 7.0
        final = clamp(final, 0.0, 100.0)

        if range_score >= 65:
            reasons.append("震荡结构较好，适合网格捕捉反复穿越")
        if backtest.score >= 65:
            reasons.append(f"最近2天网格回测较好，触发 {backtest.grid_hits} 次")
        if "trend_risk" in risk_tags:
            reasons.append("单边趋势成分偏高，需降低网格评分")
        if data.binance_ticker:
            reasons.append("Binance 同名合约数据已纳入辅助确认")

        direction = self._direction(two_day_change, slope, rsi_value, efficiency)
        confidence = clamp(45 + final * 0.45 + min(15, backtest.grid_hits), 0, 100)
        if direction == "neutral_defensive":
            confidence = min(confidence, 84.0)
        elif direction == "wait":
            confidence = min(confidence, 60.0)

        return GridScoreResult(
            symbol=data.symbol,
            final_score=round(final, 2),
            confidence=round(confidence, 2),
            direction=direction,
            atr_pct=round(atr_pct, 4),
            range_efficiency=round(efficiency, 4),
            risk_tags=list(dict.fromkeys(risk_tags)),
            reasons=reasons,
            breakdown={
                "liquidity": round(liquidity_score, 2),
                "volatility": round(volatility_score, 2),
                "range": round(range_score, 2),
                "backtest": round(backtest.score, 2),
                "funding": round(funding_score, 2),
                "binance": round(binance_score, 2),
                "risk": round(risk_score, 2),
            },
            backtest=backtest,
            hard_blocked=hard_blocked,
        )

    def rank(self, rows: list[SymbolMarketData]) -> list[GridScoreResult]:
        scores = [self.score(row) for row in rows]
        return sorted(scores, key=lambda item: item.final_score, reverse=True)

    def _liquidity_score(self, volume: float, oi_value: float, spread_bps: float) -> float:
        volume_part = clamp(volume / max(1.0, self.config.min_volume_24h) * 45, 0, 45)
        oi_part = clamp(oi_value / max(1.0, self.config.min_oi_value) * 45, 0, 45)
        spread_part = clamp(10 - spread_bps, 0, 10)
        return volume_part + oi_part + spread_part

    @staticmethod
    def _volatility_score(atr_pct: float) -> float:
        if atr_pct <= 0:
            return 0.0
        if 1.1 <= atr_pct <= 4.5:
            return 90.0 - abs(atr_pct - 2.4) * 7
        if atr_pct < 1.1:
            return max(0.0, 55.0 * atr_pct / 1.1)
        return max(0.0, 80.0 - (atr_pct - 4.5) * 13)

    @staticmethod
    def _range_score(efficiency: float, position: float, boll_width: float) -> float:
        efficiency_score = (1 - clamp(efficiency, 0, 1)) * 70
        center_score = (1 - abs(position - 0.5) * 2) * 20
        width_score = 10 if 1.0 <= boll_width <= 12.0 else 4
        return clamp(efficiency_score + center_score + width_score, 0, 100)

    @staticmethod
    def _funding_score(funding: float) -> float:
        return clamp(100 - abs(funding) / 0.0008 * 100, 0, 100)

    @staticmethod
    def _risk_score(tags: list[str]) -> float:
        penalties = {
            "low_volume": 35,
            "low_oi": 35,
            "too_low_volatility": 25,
            "too_high_volatility": 35,
            "extreme_funding": 35,
            "large_24h_move": 18,
            "trend_risk": 25,
            "near_range_edge": 15,
            "oi_spike": 15,
        }
        return clamp(100 - sum(penalties.get(tag, 0) for tag in set(tags)), 0, 100)

    @staticmethod
    def _binance_confirmation_score(data: SymbolMarketData, okx_change: float, okx_atr: float) -> float:
        if not data.binance_ticker or not data.binance_candles_15m:
            return 50.0
        binance_change = pct_change(data.binance_candles_15m[0].close, data.binance_candles_15m[-1].close)
        binance_atr = atr_percent(data.binance_candles_15m)
        disagreement = abs(binance_change - okx_change) + abs(binance_atr - okx_atr)
        return clamp(100 - disagreement * 5, 0, 100)

    @staticmethod
    def _direction(change_pct: float, slope: float, rsi_value: float, efficiency: float) -> str:
        if efficiency > 0.72:
            return "wait"
        if change_pct > 1.5 and slope >= 0 and rsi_value < 72:
            return "long_bias"
        if change_pct >= -1.0 and slope >= -1.0:
            return "neutral_light_long"
        if change_pct < -3 and slope < 0:
            return "neutral_defensive"
        return "neutral"
