# nofx 网格策略经验沉淀

## 策略 JSON 兼容点

nofx 可导入策略以如下结构为主：

- `name`
- `description`
- `config`
- `exported_at`
- `version`

网格策略关键字段：

- `config.strategy_type = "grid_trading"`
- `config.coin_source.static_coins = ["SYMBOL"]`
- `config.grid_config.symbol = "SYMBOL"`
- `config.grid_config.grid_count`
- `config.grid_config.total_investment`
- `config.grid_config.leverage`
- `config.grid_config.use_atr_bounds`
- `config.grid_config.atr_multiplier`
- `config.grid_config.distribution`
- `config.grid_config.max_drawdown_pct`
- `config.grid_config.stop_loss_pct`
- `config.grid_config.daily_loss_limit_pct`
- `config.grid_config.use_maker_only`
- `config.grid_config.enable_direction_adjust`
- `config.grid_config.direction_bias_ratio`

## 三种资金分配

`uniform`

- 每层资金相同。
- 适合非常中性的窄幅震荡。
- 缺点是上涨趋势中上方开空资金不小，下跌趋势中下方接多资金也不小。

`gaussian`

- 中间层资金更重，上下边缘更轻。
- 适合 ETH/BTC 这类中性或轻偏多网格。
- 比 uniform 更适合实际市场，因为大多数成交集中在中部区间。

`pyramid`

- 低价层资金更重，高价层资金更轻。
- 对偏多网格友好：下方回调买入更重，上方开空更轻。
- 适合 SOL 偏多、震荡上涨或不想在上涨中堆空的场景。

## direction_bias_ratio 的含义

`direction_bias_ratio` 控制 long_bias/short_bias 模式下买卖网格层数比例，不是资金比例。

例子：

- `grid_count = 8`
- `direction_bias_ratio = 0.85`

long_bias 下大约会偏向 6 个买入层、2 个卖出层。实际资金还会再叠加 `distribution` 权重，所以 `pyramid + 0.85` 会显著降低上方开空风险。

## OKX 网格方向风险

当前 nofx OKX 网格里：

- `BUY` 会开多。
- `SELL` 会开空。
- `SELL` 不是只减多仓。

因此中性网格在单边上涨时容易累积空头，在单边下跌时容易累积多头。NeuralGridSignal 的设计重点就是避免在趋势风险高时生成激进中性网格。

## SOL 和 ETH 经验模板

SOL 偏多低风险经验：

- `grid_count = 8`
- `total_investment = 180`
- `leverage = 2`
- `atr_multiplier = 2.6`
- `distribution = pyramid`
- `max_drawdown_pct = 6`
- `stop_loss_pct = 3`
- `daily_loss_limit_pct = 3`
- `direction_bias_ratio = 0.85`

ETH 中性轻偏多经验：

- `grid_count = 10`
- `total_investment = 220`
- `leverage = 2`
- `atr_multiplier = 2.3`
- `distribution = gaussian`
- `max_drawdown_pct = 7`
- `stop_loss_pct = 3.5`
- `daily_loss_limit_pct = 4`
- `direction_bias_ratio = 0.62`

NeuralGridSignal 会根据评分动态生成这些参数，但不会偏离这个风险框架太远。

防守观察经验：

- 用于 `neutral_defensive` 或评分有一定优势但方向偏弱的币种。
- 资金默认降到 120 USDT。
- 网格层数降到 7 层。
- `distribution = gaussian`。
- `direction_bias_ratio = 0.55`，接近中性但轻微保留多侧。
- ATR 倍数会比普通中性策略更宽，减少窄网格噪音成交。
- Telegram 会显示 `action: 防守观察`，这类策略不应和 `可导入` 同等对待。

## 扫描周期

网格策略一般建议：

- 标准：5 分钟。
- 保守：10 分钟。
- 高波动或行情破位：暂停或降频，不建议靠更高频率补救。

扫描周期太短会增加 AI 决策噪音和调整频率，容易把网格变成追涨杀跌。

## 同币种双账户多空网格

同一币种两个账户同时跑做多和做空网格理论上可以做风险对冲，但不适合作为默认方案：

- 手续费和资金费率会叠加。
- 两边都可能在宽幅趋势中被动累积反向仓。
- 如果没有统一风控和净敞口管理，两个账户会各自亏损。

更可行的方案是：

- 一个账户跑 SOL 偏多或趋势友好网格。
- 另一个账户跑 ETH 中性轻偏多网格。
- 用 NeuralGridSignal 每天 08:00、20:00 重新评估是否换币、暂停或降低资金。
