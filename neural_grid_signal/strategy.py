from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from neural_grid_signal.indicators import clamp
from neural_grid_signal.models import GridScoreResult, StrategyDocument


def _iso(dt: datetime | None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _grid_count(score: GridScoreResult) -> int:
    if score.recommended_grid_count > 0:
        return score.recommended_grid_count
    if score.direction == "long_bias":
        return 8 if score.atr_pct <= 4.2 else 6
    if score.direction == "neutral_light_long":
        return 10 if score.atr_pct <= 3.2 else 8
    if score.direction == "neutral_defensive":
        return 7
    return 8


def _atr_multiplier(score: GridScoreResult) -> float:
    if score.recommended_atr_multiplier > 0:
        return round(score.recommended_atr_multiplier, 2)
    if score.atr_pct <= 1.2:
        value = 2.1
    elif score.atr_pct <= 2.8:
        value = 2.35
    elif score.atr_pct <= 4.5:
        value = 2.65
    else:
        value = 3.0
    if score.direction == "long_bias":
        value += 0.15
    elif score.direction == "neutral_defensive":
        value += 0.3
    elif score.direction == "wait":
        value += 0.5
    return round(clamp(value, 2.0, 3.1), 2)


def _distribution_and_bias(score: GridScoreResult) -> tuple[str, float]:
    if score.direction == "long_bias":
        ratio = clamp(0.76 + (score.final_score - 70) / 100, 0.75, 0.85)
        return "pyramid", round(ratio, 2)
    if score.direction == "neutral_light_long":
        ratio = clamp(0.60 + (score.final_score - 70) / 250, 0.58, 0.68)
        return "gaussian", round(ratio, 2)
    if score.direction == "neutral_defensive":
        return "gaussian", 0.55
    return "gaussian", 0.58


def _style_for_direction(direction: str, distribution: str) -> str:
    if direction == "neutral_defensive":
        return "防守观察"
    if direction == "wait":
        return "等待观察"
    return "偏多低风险" if distribution == "pyramid" else "中性轻偏多"


def _risk_params(score: GridScoreResult) -> tuple[float, float, float]:
    stop_loss = round(clamp(score.atr_pct * 1.25, 2.5, 4.5), 2)
    daily_loss = round(clamp(stop_loss + 0.5, 3.0, 5.0), 2)
    max_drawdown = round(clamp(stop_loss * 2.0, 5.0, 8.0), 2)
    return max_drawdown, stop_loss, daily_loss


def _prompt_sections(symbol: str, direction: str) -> dict[str, str]:
    base = symbol.replace("USDT", "")
    if direction == "long_bias":
        style = "偏多低风险"
        direction_text = "优先保留回调买入网格，减少上涨趋势中上方开空的资金权重。"
    elif direction == "neutral_defensive":
        style = "防守观察"
        direction_text = "当前结构适合观察或小资金低密度网格，不适合扩大仓位。"
    elif direction == "wait":
        style = "等待观察"
        direction_text = "当前趋势风险偏高，优先等待，不建议直接导入执行。"
    else:
        style = "中性轻偏多"
        direction_text = "保留双向震荡收益，但当结构转强时降低空侧暴露。"
    return {
        "role_definition": f"# 你是专业的 {symbol} {style}网格交易员\n\n你的任务是在 {symbol} 上执行低杠杆、低回撤的智能网格。{direction_text}",
        "trading_frequency": "# 网格频率认知\n\n- 默认使用 5m 扫描周期，市场波动扩大时可降频到 10m\n- 不为了补网扩大总风险\n- 突破上沿或下沿后优先暂停、等待或调整网格",
        "entry_standards": f"# 网格执行标准\n\n1. 仅交易 {symbol}\n2. 优先 maker-only，避免手续费侵蚀\n3. Funding 极端、OI 急增、价格贴近区间边缘时暂停新增网格\n4. 单边趋势确认后不逆势加仓\n5. 网格资金以低杠杆和低回撤为第一目标",
        "decision_process": f"# 决策流程\n\n1. 判断 {base} 在 5m、15m、1h、4h 上是震荡、偏多震荡还是趋势\n2. 检查 ATR、布林带宽度、EMA 距离、RSI、OI、Funding\n3. 区间有效时保持网格\n4. 趋势突破时降低反向暴露或暂停\n5. 回到区间中部后再恢复网格密度",
    }


def _common_config(symbol: str, grid_config: dict[str, Any], min_confidence: int, direction: str) -> dict[str, Any]:
    return {
        "strategy_type": "grid_trading",
        "language": "zh",
        "coin_source": {
            "source_type": "static",
            "static_coins": [symbol],
            "use_ai500": False,
            "ai500_limit": 3,
            "use_oi_top": False,
            "oi_top_limit": 3,
            "use_oi_low": False,
            "oi_low_limit": 3,
            "use_hyper_all": False,
            "use_hyper_main": False,
        },
        "indicators": {
            "klines": {
                "primary_timeframe": "5m",
                "primary_count": 24,
                "longer_timeframe": "4h",
                "longer_count": 16,
                "enable_multi_timeframe": True,
                "selected_timeframes": ["5m", "15m", "1h", "4h"],
            },
            "enable_raw_klines": True,
            "enable_ema": True,
            "enable_macd": True,
            "enable_rsi": True,
            "enable_atr": True,
            "enable_boll": True,
            "enable_volume": True,
            "enable_oi": True,
            "enable_funding_rate": True,
            "ema_periods": [20, 50],
            "rsi_periods": [7, 14],
            "atr_periods": [14],
            "boll_periods": [20],
            "nofxos_api_key": "cm_568c67eae410d912c54c",
            "enable_quant_data": True,
            "enable_quant_oi": True,
            "enable_quant_netflow": True,
            "enable_oi_ranking": True,
            "oi_ranking_duration": "1h",
            "oi_ranking_limit": 10,
            "enable_netflow_ranking": True,
            "netflow_ranking_duration": "1h",
            "netflow_ranking_limit": 10,
            "enable_price_ranking": True,
            "price_ranking_duration": "1h,4h,24h",
            "price_ranking_limit": 10,
        },
        "risk_control": {
            "max_positions": 1,
            "btc_eth_max_leverage": 2,
            "altcoin_max_leverage": 2,
            "btc_eth_max_position_value_ratio": 0.65,
            "altcoin_max_position_value_ratio": 0.45,
            "max_margin_usage": 0.32,
            "min_position_size": 12,
            "min_risk_reward_ratio": 2.4,
            "min_confidence": min_confidence,
        },
        "prompt_sections": _prompt_sections(symbol, direction),
        "grid_config": grid_config,
    }


def build_strategy_document(
    score: GridScoreResult,
    exported_at: datetime | None = None,
    *,
    investment: float = 500,
) -> StrategyDocument:
    symbol = score.symbol.upper()
    distribution, bias = _distribution_and_bias(score)
    max_drawdown, stop_loss, daily_loss = _risk_params(score)
    grid_config = {
        "symbol": symbol,
        "grid_count": _grid_count(score),
        "total_investment": round(float(investment), 2),
        "leverage": 2,
        "upper_price": 0,
        "lower_price": 0,
        "use_atr_bounds": True,
        "atr_multiplier": _atr_multiplier(score),
        "distribution": distribution,
        "max_drawdown_pct": max_drawdown,
        "stop_loss_pct": stop_loss,
        "daily_loss_limit_pct": daily_loss,
        "use_maker_only": True,
        "enable_direction_adjust": True,
        "direction_bias_ratio": bias,
    }
    style = _style_for_direction(score.direction, distribution)
    config = _common_config(symbol, grid_config, min_confidence=int(clamp(score.confidence, 72, 86)), direction=score.direction)
    return StrategyDocument(
        name=f"{symbol.replace('USDT', '')} 网格·AI信号·{style}",
        description=f"由 NeuralGridSignal 生成。评分 {score.final_score:.1f}，方向 {score.direction}，ATR {score.atr_pct:.2f}%。",
        config=config,
        exported_at=_iso(exported_at),
    )
