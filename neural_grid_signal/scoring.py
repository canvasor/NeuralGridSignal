from __future__ import annotations

import statistics
from dataclasses import dataclass

from neural_grid_signal.backtest import optimize_grid
from neural_grid_signal.indicators import (
    atr,
    atr_percent,
    bollinger_width_percent,
    clamp,
    close_position_in_range,
    ema_slope_percent,
    pct_change,
    range_efficiency,
    rsi,
)
from neural_grid_signal.models import BacktestResult, Candle, GridScoreResult, NofxPreflight, SymbolMarketData


@dataclass(frozen=True)
class ScoringConfig:
    min_volume_24h: float = 10_000_000
    min_oi_value: float = 10_000_000
    min_atr_pct: float = 0.35
    max_atr_pct: float = 8.0
    extreme_funding_abs: float = 0.0008
    max_abs_24h_change: float = 18.0
    investment: float = 500
    nofx_min_display_spacing: float = 0.005


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
        bound_atr = atr(data.okx_candles_4h or long_candles)
        backtest = optimize_grid(
            candles,
            investment=self.config.investment,
            bound_atr=bound_atr,
            min_spacing=self.config.nofx_min_display_spacing,
        )
        nofx_preflight = self._nofx_preflight(data, backtest)

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
        slow_downtrend = two_day_change < -4 and slope < -0.2
        slow_uptrend = two_day_change > 8 and slope > 0.35
        if efficiency > 0.62 or abs(two_day_change) > 10 or abs(slope) > 1.8 or slow_downtrend or slow_uptrend:
            risk_tags.append("trend_risk")
        if position < 0.08 or position > 0.92:
            risk_tags.append("near_range_edge")
        else:
            risk_tags.append("near_range_middle")
        if abs(oi_change) > 12:
            risk_tags.append("oi_spike")
        risk_tags.extend(nofx_preflight.risk_tags)
        if nofx_preflight.verdict == "reject":
            hard_blocked = True

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
            final -= 18.0 if slow_downtrend else 14.0
        if "near_range_edge" in risk_tags:
            final -= 7.0
        if nofx_preflight.verdict == "caution":
            final -= 8.0
        final = clamp(final, 0.0, 100.0)

        if range_score >= 65:
            reasons.append("震荡结构较好，适合网格捕捉反复穿越")
        if backtest.score >= 65:
            reasons.append(f"最近2天网格回测较好，触发 {backtest.grid_hits} 次")
        if "trend_risk" in risk_tags:
            reasons.append("单边趋势成分偏高，需降低网格评分")
        if nofx_preflight.verdict == "reject":
            reasons.append("nofx 运行时预检不通过，导入后大概率会暂停或持有")
        elif nofx_preflight.verdict == "caution":
            reasons.append("nofx 运行时预检提示谨慎，需降低评分")
        if data.binance_ticker:
            reasons.append("Binance 同名合约数据已纳入辅助确认")

        direction = self._direction(two_day_change, slope, rsi_value, efficiency)
        if nofx_preflight.verdict == "reject":
            direction = "wait"
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
            recommended_grid_count=backtest.grid_count or 8,
            recommended_atr_multiplier=backtest.atr_multiplier or 2.4,
            grid_lower_price=backtest.lower_price,
            grid_upper_price=backtest.upper_price,
            nofx_preflight=nofx_preflight,
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

    def _nofx_preflight(self, data: SymbolMarketData, backtest: BacktestResult) -> NofxPreflight:
        candles = data.binance_candles_5m or data.okx_candles_5m
        source = "binance_5m" if data.binance_candles_5m else "okx_5m" if data.okx_candles_5m else "missing"
        if not candles:
            return NofxPreflight(source=source, verdict="unknown", risk_tags=["nofx_preflight_missing_5m"])

        current_price = candles[-1].close
        lower_band, middle_band, upper_band = self._bollinger_bands(candles)
        boll_width = bollinger_width_percent(candles)
        band_position = 0.5
        position_label = "middle"
        if upper_band > lower_band:
            band_position = clamp((current_price - lower_band) / (upper_band - lower_band), 0.0, 1.0)
            if band_position >= 0.8:
                position_label = "upper"
            elif band_position <= 0.2:
                position_label = "lower"

        grid_spacing = 0.0
        grid_range_pct = 0.0
        grid_spacing_pct = 0.0
        if backtest.upper_price > backtest.lower_price and backtest.grid_count > 1 and current_price > 0:
            grid_spacing = (backtest.upper_price - backtest.lower_price) / (backtest.grid_count - 1)
            grid_range_pct = (backtest.upper_price - backtest.lower_price) / current_price * 100
            grid_spacing_pct = grid_spacing / current_price * 100

        display_spacing_ok = grid_spacing >= self.config.nofx_min_display_spacing
        change_1h = self._change_by_bars(candles, 12)
        change_4h = self._change_by_bars(candles, 48)
        rsi_5m = rsi(candles)
        atr_pct_5m = atr_percent(candles)
        risk_tags: list[str] = []

        if boll_width > 4.0:
            risk_tags.append("wide_5m_bollinger")
        if abs(change_4h) > 5.0:
            risk_tags.append("strong_4h_move")
        if position_label == "upper":
            risk_tags.append("near_bollinger_upper")
        elif position_label == "lower":
            risk_tags.append("near_bollinger_lower")
        if rsi_5m >= 65 and change_4h > 0:
            risk_tags.append("rsi_uptrend_risk")
        elif rsi_5m <= 35 and change_4h < 0:
            risk_tags.append("rsi_downtrend_risk")
        if not display_spacing_ok:
            risk_tags.append("nofx_spacing_rounds_to_zero")

        reject = not display_spacing_ok or (
            boll_width > 4.0
            and (abs(change_4h) > 5.0 or position_label != "middle" or "rsi_uptrend_risk" in risk_tags or "rsi_downtrend_risk" in risk_tags)
        )
        if reject:
            risk_tags.append("nofx_runtime_reject")
            verdict = "reject"
        elif boll_width > 3.0 or abs(change_4h) > 3.5 or position_label != "middle":
            verdict = "caution"
        else:
            verdict = "pass"

        return NofxPreflight(
            source=source,
            verdict=verdict,
            bollinger_width_5m=round(boll_width, 4),
            atr_pct_5m=round(atr_pct_5m, 4),
            rsi_5m=round(rsi_5m, 2),
            price_change_1h=round(change_1h, 4),
            price_change_4h=round(change_4h, 4),
            bollinger_position=round(band_position, 4),
            bollinger_position_label=position_label,
            grid_range_pct=round(grid_range_pct, 4),
            grid_spacing=round(grid_spacing, 8),
            grid_spacing_pct=round(grid_spacing_pct, 4),
            display_spacing_ok=display_spacing_ok,
            risk_tags=list(dict.fromkeys(risk_tags)),
        )

    @staticmethod
    def _bollinger_bands(candles: list[Candle], period: int = 20, stdevs: float = 2.0) -> tuple[float, float, float]:
        closes = [c.close for c in candles if c.close > 0]
        if not closes:
            return 0.0, 0.0, 0.0
        window = closes[-period:] if len(closes) >= period else closes
        middle = statistics.fmean(window)
        sigma = statistics.pstdev(window) if len(window) > 1 else 0.0
        return middle - stdevs * sigma, middle, middle + stdevs * sigma

    @staticmethod
    def _change_by_bars(candles: list[Candle], bars: int) -> float:
        if not candles:
            return 0.0
        start_index = -bars - 1 if len(candles) > bars else 0
        return pct_change(candles[start_index].close, candles[-1].close)

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
