# NeuralGridSignal

OKX 合约智能网格信号辅助系统。系统扫描 OKX USDT 永续合约，并用 Binance Futures 数据做辅助确认，选出最近 2 天更适合运行低风险网格的币种，生成 nofx 可导入策略 JSON，并通过 Telegram 推送关键参数。

## 核心能力

- OKX 主市场扫描：ticker、K 线、资金费率、OI、盘口。
- Binance 辅助确认：ticker、K 线、资金费率、OI。
- 最近 2 天轻量网格回测。
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
