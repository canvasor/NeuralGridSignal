# NeuralGridSignal 架构设计

## 背景

NeuralGridSignal 是 OKX 合约智能网格信号辅助系统。系统不直接下单，只扫描 OKX USDT 永续合约市场，并用 Binance 合约数据做交叉验证，选出最近 2 天更适合运行 nofx 网格策略的币种，生成 nofx 可导入策略 JSON，并把关键参数通过 Telegram 发出。

项目参考了本机 `/home/admin/MarketDataService` 的行情采集口径：

- OKX 使用公共行情接口获取 SWAP instruments、tickers、candles、funding、open interest、orderbook。
- Binance 使用 Futures 公共接口获取 exchangeInfo、24h tickers、klines、funding、OI 历史。
- 不使用 valuescan，因为稳定性不适合生产级定时信号。

项目也参考了 `/home/admin/nofx` 的网格策略格式和运行行为：

- 可导入策略 JSON 顶层包含 `name`、`description`、`config`、`exported_at`、`version`。
- `config.strategy_type` 必须为 `grid_trading`。
- `config.grid_config` 中有效字段以 nofx `store.GridStrategyConfig` 为准。
- `distribution` 支持 `uniform`、`gaussian`、`pyramid`。
- `direction_bias_ratio` 是 long_bias/short_bias 下买卖网格层数比例，不是资金比例。
- nofx 当前网格中 `SELL` 是开空，不是只减仓；因此上涨趋势下必须控制空侧层数和上方资金权重。

## 系统边界

系统负责：

- 扫描候选 OKX USDT 永续合约。
- 拉取 OKX 主行情数据。
- 拉取 Binance 辅助行情数据。
- 计算网格适配评分、风险评分、历史 2 天模拟网格表现，并搜索最佳网格数和 ATR 倍数。
- 可选调用 OpenAI 兼容模型做结构化复核。
- 输出 nofx 可导入策略 JSON。
- 通过 Telegram 发送简洁行动通知和扫描池统计。
- 支持一次性运行和北京时间 08:00、20:00 定时运行。

系统不负责：

- 不读取账户资产。
- 不下单、不撤单、不管理持仓。
- 不替代 nofx 的执行风控。
- 不追求预测单边方向，只判断是否适合低风险网格。

## 模块

`neural_grid_signal.config`

- 读取环境变量和默认参数。
- 交易所、Telegram、OpenAI 配置均从环境变量读取。
- 默认调度时区为 `Asia/Shanghai`，默认时间为 `08:00,20:00`。

`neural_grid_signal.models`

- 定义行情、评分、网格参数、策略文档等 dataclass。
- 所有核心算法使用这些结构，便于测试和离线回放。

`neural_grid_signal.exchanges.okx`

- OKX 公共 REST 客户端。
- 负责 OKX 可交易合约列表、ticker、K 线、资金费率、OI、盘口。

`neural_grid_signal.exchanges.binance`

- Binance Futures 公共 REST 客户端。
- 负责候选币辅助确认：ticker、K 线、资金费率、OI 历史。

`neural_grid_signal.indicators`

- ATR、RSI、布林带宽度、EMA 斜率、区间效率、最大回撤等指标。
- 不依赖 pandas/numpy，降低部署复杂度。

`neural_grid_signal.backtest`

- 用最近 2 天 15m K 线做 nofx-compatible 轻量回测。
- 按单根 K 线的 `open -> high/low -> low/high -> close` 路径估算网格层触发，而不是只看收盘价穿越。
- 输出网格触发次数、收益代理、最大库存偏移、最大回撤代理、稳定性评分。
- 回测边界按 nofx 的 ATR 公式估算：当前价 ± `4h ATR14 * atr_multiplier`。
- 策略 JSON 默认导出显式 `lower_price` / `upper_price`，避免 nofx 容器运行时 ATR 自动边界回退成过窄默认范围。
- 回测会在多个 `grid_count` 和 `atr_multiplier` 组合中搜索综合分最高的参数。

`neural_grid_signal.scoring`

- 聚合评分主逻辑。
- 输出候选币总分、子维度分、风险标签、推荐方向倾向。
- 增加 nofx runtime preflight：优先使用 Binance 5m 数据，其次回退到 OKX 5m，用布林带宽度、4h 涨跌、RSI、布林位置和网格显示间距预估 nofx AI 是否会暂停网格。
- 最终只会为 `NOFX Preflight = pass` 的候选生成策略；否则输出 `no_signal`。

`neural_grid_signal.strategy`

- 根据候选币评分和 nofx 模板经验生成完整策略 JSON。
- 优先生成低杠杆、低资金占用、显式上下边界策略。
- `total_investment` 默认 500 USDT，可由 `GRID_SIGNAL_INVESTMENT_USDT` 或 `--investment` 覆盖，并同步用于回测。

`neural_grid_signal.openai_decider`

- 可选复核层。
- 当 `OPEN_AI_ENDPOINT`、`OPEN_AI_MODEL`、`OPEN_AI_API_KEY` 均存在时启用。
- 只允许返回结构化建议，不允许覆盖硬风控。

`neural_grid_signal.notifier`

- Telegram 通知。
- 通知包含扫描池统计、入选币种、评分、趋势状态、本金、网格层数、显式网格上下沿、nofx 预检结果、ATR 倍数、分配方式、回测摘要、止损和生成文件路径。

`neural_grid_signal.runner`

- 编排一次扫描：采集、评分、复核、生成策略或 `no_signal` 结果、通知、落盘。
- 每次运行都会额外写入 `output/runs/*.json` 快照，便于复盘候选池和预检结果。

`neural_grid_signal.scheduler`

- 计算北京时间下一次运行时间。
- 支持 `--once`、`--dry-run`、`--schedule`。

## 选币总流程

1. 获取 OKX USDT 永续合约列表。
2. 获取 OKX tickers，先按 `GRID_SIGNAL_MIN_CONTRACT_VOLUME_24H` 过滤低合约成交额币种，再取前 `GRID_SIGNAL_CANDIDATE_LIMIT` 个进入详细行情拉取。
3. 对候选币获取最近 5m K 线用于 nofx 运行时预检，同时获取最近 2 天 15m K 线、最近 7 天 1h K 线、4h ATR 上下文、funding、OI、盘口。
4. 如果 Binance 存在同名 USDT 永续合约，拉取 Binance 对应数据做辅助确认。
5. 计算网格适配分：
   - 流动性分：OKX 24h 成交额、OI、盘口价差。
   - 波动适配分：ATR% 不能太低，也不能过高。
   - 震荡质量分：区间效率低、布林带宽度适中、价格不贴近边界。
   - 趋势风险分：强单边、连续突破、价格远离 EMA 时扣分。
   - nofx 兼容分：5m 布林带过宽、4h 强趋势、价格贴近布林边缘或 nofx 显示网格间距会变成 `$0.00` 时降分或过滤。
   - 资金风险分：极端 funding、OI 快速异常扩张时扣分。
   - Binance 确认分：两个交易所方向和波动结构一致时加分，分歧时降权。
   - 2 天网格回测分：网格触发多、库存偏移低、回撤代理低时加分。
6. 选择最高分且通过硬风控的币种。
7. 根据回测搜索结果生成 `grid_count`、`atr_multiplier`、范围说明和 nofx 策略 JSON。
8. Telegram 发送结果，包含扫描池统计、本金、网格参数、范围和回测摘要。

## 硬风控

任何候选币命中以下条件，默认不推荐或强降权：

- OKX 24h 成交额低于配置阈值。
- OI 价值低于配置阈值。
- ATR% 低于 `0.35%`，网格空间不足。
- ATR% 高于 `8%`，容易突破与扫损。
- 最近 2 天区间效率偏高，或 EMA 斜率/2 天涨跌幅显示缓慢单边趋势。
- 当前价格距离 2 天高低点任一边界小于 `8%` 区间宽度，突破风险高。
- funding 绝对值高于 `0.08%`。
- 最近 24h 涨跌幅绝对值高于 `18%`。

## 策略参数原则

偏多网格：

- `distribution = pyramid`
- `direction_bias_ratio = 0.75 - 0.85`
- `grid_count` 和 `atr_multiplier` 由回测搜索确定。
- `leverage = 2`
- 适合震荡上涨、温和上升通道、回调买入更重要的币。

中性轻偏多网格：

- `distribution = gaussian`
- `direction_bias_ratio = 0.58 - 0.68`
- `grid_count` 和 `atr_multiplier` 由回测搜索确定。
- `leverage = 2`
- 适合 ETH/BTC 类更稳币种，或短线没有明确方向但结构不弱的币。

观望网格：

- 仍生成可导入策略，但通知标记为防守观察；本金默认 500 USDT，可通过启动参数或环境变量调整。
- 用于评分勉强合格但风险标签较多时。

## 输出

每次运行输出：

- `output/strategies/YYYYMMDD_HHMM_<SYMBOL>_grid_signal.json`
- `output/reports/YYYYMMDD_HHMM_<SYMBOL>_grid_signal.md`
- Telegram 通知摘要

## 部署

推荐生产运行方式：

```bash
python -m neural_grid_signal --once
python -m neural_grid_signal --schedule
```

定时任务可以用系统 cron/systemd 调用 `--once`，也可以让进程常驻用内置 scheduler。北京时间明天 08:00 和 20:00 的首次运行可通过系统 cron 更稳；内置 scheduler 会自动按本地配置循环。
