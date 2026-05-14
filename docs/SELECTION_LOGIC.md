# 选币逻辑和参数生成说明

## 目标

系统不是预测哪个币一定上涨，而是寻找未来 1-2 天更适合低风险网格的 OKX 合约币种。最优目标是：有足够波动、有足够成交和 OI、价格在区间中部附近、单边趋势风险不高、最近 2 天网格触发质量好。

## 候选池

默认从 OKX USDT 永续合约中先按 `GRID_SIGNAL_MIN_CONTRACT_VOLUME_24H` 过滤 24h 合约成交额，再从通过流动性过滤的币种中按成交额排序，取前 `GRID_SIGNAL_CANDIDATE_LIMIT` 个进入详细行情拉取和评分。

报告和 Telegram 会记录：

- OKX 合约总数。
- 通过流动性过滤数量。
- 被流动性过滤掉数量。
- 进入网格评分池数量。
- 通过硬风控数量。

Binance 数据只做辅助：

- 同名 Binance Futures 合约存在时，比较 2 天涨跌幅和 ATR 是否与 OKX 接近。
- Binance 缺失时不直接淘汰，但辅助确认分为中性。
- Binance 与 OKX 分歧越大，辅助确认分越低。

## 硬风控

命中以下条件会 hard block 或显著降权：

- `low_volume`：OKX 24h 成交额低于配置阈值。
- `low_oi`：OKX OI 价值低于配置阈值。
- `too_low_volatility`：ATR% 低于 0.35%，网格空间不足。
- `too_high_volatility`：ATR% 高于 8%，突破和扫损风险高。
- `extreme_funding`：资金费率绝对值高于 0.08%。
- `large_24h_move`：24h 涨跌幅绝对值高于 18%。
- `trend_risk`：2 天区间效率过高、EMA 斜率过大、2 天涨跌幅过大，或出现缓慢单边上行/下行。
- `near_range_edge`：当前价格贴近 2 天区间边界。
- `oi_spike`：短期 OI 异常扩张。

## 子评分

总分 0-100，主要由以下维度组成：

- `liquidity`：成交额、OI、盘口价差。
- `volatility`：ATR% 是否位于适合网格的甜区。
- `range`：区间效率、价格是否靠近区间中部、布林带宽度是否适中。
- `backtest`：最近 2 天轻量网格模拟表现。
- `funding`：资金费率是否温和。
- `binance`：Binance 与 OKX 是否确认同一市场结构。
- `risk`：风险标签扣分后的保守分。

权重在 `neural_grid_signal/scoring.py` 中固定。后续调参应优先改权重和阈值，不要直接让 LLM 改写硬风控。

## 区间效率

区间效率定义为：

```text
abs(last_close - first_close) / sum(abs(close[i] - close[i-1]))
```

含义：

- 接近 0：来回震荡，适合网格。
- 接近 1：单边移动，不适合中性网格。

这是避免“单边上涨开空越开越亏、单边下跌做多越接越亏”的核心过滤器。

## 2 天轻量网格回测

回测不模拟真实交易所成交队列，只做结构判断：

- 使用和 nofx 运行时一致的 ATR 边界公式：当前价 ± `4h ATR14 * atr_multiplier`。
- 在多个 `grid_count` 与 `atr_multiplier` 组合中搜索综合分最高的参数。
- 统计 K 线收盘价穿越网格层次数。
- 穿越越多，说明网格触发潜力越高。
- 库存偏移越大，说明单边风险越高。
- 最大回撤越大，评分越低。
- 收益代理、最大回撤、网格上下沿、最佳网格数和 ATR 倍数会写入报告和通知。

该回测是选币维度，不是收益承诺。

## 方向分类

`direction` 用于生成策略参数：

- `long_bias`：偏多网格。适合震荡上涨或温和偏多环境。
- `neutral_light_long`：中性轻偏多。适合 ETH/BTC 类或方向不极端的宽幅震荡。
- `neutral_defensive`：防守观察。通常不应加大资金。
- `wait`：趋势风险过高，建议不执行或等待。

## 参数生成

偏多网格：

- `distribution = pyramid`
- `direction_bias_ratio = 0.75 - 0.85`
- `grid_count = 6 - 8`
- `atr_multiplier = 2.4 - 3.1`
- `leverage = 2`

中性轻偏多：

- `distribution = gaussian`
- `direction_bias_ratio = 0.58 - 0.68`
- `grid_count = 8 - 10`
- `atr_multiplier = 2.1 - 2.7`
- `leverage = 2`

防守观察：

- `distribution = gaussian`
- `direction_bias_ratio = 0.55`
- `grid_count`、`atr_multiplier` 由回测搜索结果决定
- `total_investment` 默认使用 `GRID_SIGNAL_INVESTMENT_USDT=500`，也可以用 `--investment` 覆盖
- 只适合作为观察或小资金低密度网格，导入前需要人工确认区间仍有效

本金：

- 默认 `500` USDT。
- 环境变量：`GRID_SIGNAL_INVESTMENT_USDT`。
- 命令行：`--investment 750`。
- 本金会同时应用到策略 JSON 的 `grid_config.total_investment` 和回测。

止损参数：

- `stop_loss_pct` 基于 ATR% 生成，限制在 2.5%-4.5%。
- `daily_loss_limit_pct` 通常比单次止损略宽。
- `max_drawdown_pct` 通常为止损的约 2 倍，但限制在 5%-8%。

## 调参建议

生产观察 1-2 周后再调：

- 如果选出的币太少，先降低 `GRID_SIGNAL_MIN_OI_VALUE`，不要放宽 ATR 上限。
- 如果经常选到单边币，提高 `trend_risk` 扣分或降低区间效率阈值。
- 如果网格触发太少，提高候选 ATR 甜区下限。
- 如果回撤偏大，提高成交额/OI 阈值，或降低 `--investment`；`grid_count` 和 `atr_multiplier` 当前由回测搜索决定。

## Telegram 通知解释

通知中的 `action` 是移动端执行优先级：

- `可导入`：评分和方向都通过低风险网格要求，可以按通知参数导入 nofx。
- `防守观察`：系统认为有震荡结构，但方向偏弱或风险不够干净；建议小资金观察，或等下一次 08:00/20:00 复核。
- `人工复核`：评分未到强推荐，导入前要看报告和行情结构。
- `等待`：硬风控或趋势风险未通过，不建议执行。
