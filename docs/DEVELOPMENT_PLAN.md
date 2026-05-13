# NeuralGridSignal 开发计划

## 目标

构建一个可独立维护的 OKX 合约智能网格信号辅助系统，完成行情扫描、选币评分、历史网格回测、nofx 策略 JSON 生成、Telegram 通知和定时运行。

## 阶段 1：项目骨架

- 建立 Python 包结构。
- 建立 `pyproject.toml`、`.env.example`、`README.md`。
- 建立 `docs/ARCHITECTURE.md` 和开发计划。
- 约束依赖为 `httpx`、`pytest`，核心算法不依赖 pandas/numpy。

验收：

- `python -m neural_grid_signal --help` 可运行。
- 单测可发现测试目录。

## 阶段 2：核心数据结构和配置

- 实现 `config.py`，读取用户提供的 OKX、Binance、Telegram、OpenAI 环境变量。
- 实现 `models.py`，定义 Candle、Ticker、MarketSnapshot、ScoreBreakdown、GridParameters、StrategyDocument。
- 实现时间调度工具，支持 `Asia/Shanghai` 08:00、20:00。

验收：

- 配置默认值和环境变量覆盖有单测。
- 调度下一次运行时间有单测。

## 阶段 3：指标、评分和回测

- 实现 ATR%、EMA 斜率、RSI、布林带宽度、区间效率、最大回撤。
- 实现 2 天轻量网格回测。
- 实现网格适配评分模型。
- 加入 Binance 辅助确认和硬风控标签。

验收：

- 震荡样本评分高于单边样本。
- 极端 funding、极端波动、低流动性样本被降权。
- 回测能区分高触发低回撤和低触发高偏移场景。

## 阶段 4：策略 JSON 生成

- 以 `/home/admin/nofx/strategies/09_网格_SOL_偏多低风险.json` 和 `10_网格_ETH_中性轻偏多.json` 为模板经验。
- 生成完整 nofx 可导入 JSON。
- 根据评分动态设置：
  - `grid_count`
  - `total_investment`
  - `atr_multiplier`
  - `distribution`
  - `direction_bias_ratio`
  - `stop_loss_pct`
  - `daily_loss_limit_pct`

验收：

- 生成 JSON 可被 `json.load` 正确读取。
- `config.strategy_type == "grid_trading"`。
- `coin_source.static_coins` 与 `grid_config.symbol` 一致。

## 阶段 5：交易所客户端和运行器

- 实现 OKX 公共 REST 客户端。
- 实现 Binance Futures 公共 REST 客户端。
- 实现扫描编排器。
- 支持 `--once`、`--dry-run`、`--limit`、`--schedule`。
- 不使用 valuescan。

验收：

- 交易所客户端可用 mock transport 单测覆盖。
- runner 可在 fake collector 下生成策略文件和报告。

## 阶段 6：OpenAI 复核和 Telegram 通知

- 实现 OpenAI 兼容接口调用。
- LLM 只做复核，不允许绕过硬风控。
- 实现 Telegram 通知，支持 dry-run。
- 通知内容只包含移动端执行所需关键信息。

验收：

- OpenAI 缺配置时自动跳过。
- Telegram 缺配置时不报错，返回 skipped。
- Telegram mock transport 单测覆盖消息体。

## 阶段 7：文档和生产化

- 写 `docs/SELECTION_LOGIC.md`，说明选币算法和参数含义。
- 写 `docs/OPERATIONS.md`，说明部署、定时任务、环境变量和故障处理。
- 写 `docs/NOFX_GRID_EXPERIENCE.md`，沉淀 nofx 网格策略经验。
- 补齐 README。

验收：

- 新维护者只看 README 和 docs 即可理解项目背景、运行方式、选币逻辑和 nofx 兼容注意事项。

## 阶段 8：验证

- 运行全部单元测试。
- 运行语法编译检查。
- 至少验证一次 dry-run 输出链路。

验收：

- `python -m pytest -q` 通过。
- `python -m compileall neural_grid_signal` 通过。
- dry-run 不访问真实 Telegram 下单，不需要交易权限。
