# NeuralGridSignal

OKX 合约智能网格信号辅助系统。系统扫描 OKX USDT 永续合约，并用 Binance Futures 数据做辅助确认，选出最近 2 天更适合运行低风险网格的币种，生成 nofx 可导入策略 JSON，并通过 Telegram 推送关键参数。

## 核心能力

- OKX 主市场扫描：ticker、K 线、资金费率、OI、盘口。
- Binance 辅助确认：ticker、K 线、资金费率、OI。
- 最近 2 天 nofx-compatible 轻量网格回测，按 K 线路径估算网格触发。
- `NOFX Preflight`：优先使用 Binance 5m 数据预检 nofx 运行时是否会接受该币种。
- 日线趋势风控：下跌延续或贴近日线低位的币种会被硬拦截或降权。
- 网格范围风控：偏好更窄的有效区间，避免用过宽范围换取虚高 hits。
- `pass-only` 选币：没有候选通过 nofx 预检时输出 `no_signal`，只写报告和运行快照，不生成策略 JSON。
- 网格适配评分和硬风控过滤。
- nofx `grid_trading` 策略 JSON 生成。
- Telegram 通知。
- 支持一次性运行和北京时间 08:00、20:00 常驻调度。

## 快速运行

```bash
cd /home/admin/NeuralGridSignal
python3 -m neural_grid_signal --once --dry-run
python3 -m neural_grid_signal --schedule
```

后台常驻：

```bash
./scripts/start_scheduler.sh
./scripts/status_scheduler.sh
./scripts/stop_scheduler.sh
```

后台启动时可以把参数直接传给调度进程：

```bash
./scripts/start_scheduler.sh --investment 500 --limit 80
```

如果调度器已经在运行，启动脚本不会替换参数；需要先停止再用新参数启动：

```bash
./scripts/stop_scheduler.sh
./scripts/start_scheduler.sh --investment 750 --limit 80
```

输出目录：

- `output/strategies/`：nofx 可导入策略 JSON
- `output/reports/`：本次选币评分报告

## 环境变量

复制 `.env.example` 后按服务器环境配置。行情接口主要使用公共接口，OKX/Binance 只读 key 作为后续扩展预留。

必需通知变量：

- `TELEGRAM_BOT_TOKEN_GRID`
- `TELEGRAM_CHANNEL_ID_GRID`

可选 OpenAI 复核变量：

- `OPEN_AI_ENDPOINT`
- `OPEN_AI_MODEL`
- `OPEN_AI_API_KEY`

常用运行参数：

- `--investment 500`：网格本金，默认 500 USDT。
- `--limit 80`：进入详细行情拉取和评分的候选数量上限。
- `--log-level DEBUG`：调试日志级别。

## 测试

```bash
python3 -m pytest -q
python3 -m compileall neural_grid_signal
```

## 文档

- `docs/ARCHITECTURE.md`：系统架构
- `docs/DEVELOPMENT_PLAN.md`：开发计划
- `docs/SELECTION_LOGIC.md`：选币和参数生成逻辑
- `docs/OPERATIONS.md`：生产运行和定时任务
- `docs/NOFX_GRID_EXPERIENCE.md`：nofx 网格策略兼容经验

## 2026-11-24 信号质量修复

发布除预检pass外，要求总分至少55（GRID_SIGNAL_MIN_SCORE）、方向非wait、无trend_risk、日线已知，
并有Binance 5m执行数据，历史模型计费后净权益为正。Binance优先确定15m评分/导出区间和日线，OKX继续作为流动性候选池；
两市场ticker价差超过1%硬拒绝，执行价在网格外也拒绝。
K线排除未收盘数据；每次最多同时构建2个币种（GRID_SIGNAL_MAX_SYMBOL_CONCURRENCY，最多4）。
轻量评分网格改用历史前段固定区间，不用末价回看；有限库存、双边费用、真实亏损和期末浮盈亏计入，
额外字段evaluation_lower_price/evaluation_upper_price/net_equity_return_pct保留审计口径。
这仍是参数筛选的简化回放，不含完整资金费/盘口/强平或独立样本验证，不是Paper收益等价物。
JSON原子发布；快照selection_policy/candidate_diagnostics解释拒绝原因。单次任务异常不退出调度器。
55分是新评分下初始质量门槛，需要后续采样，不能用旧分数直接比较新算法收益。
维护时GRID_SIGNAL_QUIET_LIFECYCLE=1仅关闭启停提示，不影响原有定时信号通知。
详细设计、测试与部署证据在/data/nofx/NofxStrategyFactory/docs/neural-grid-signal-optimization-2026-11-24.md。
