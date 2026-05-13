# 生产运行说明

## 环境

推荐在 `/home/admin/NeuralGridSignal` 独立维护。项目当前仅依赖 Python 标准库和 pytest 测试工具，运行不需要 pandas/numpy。

## 一次性运行

```bash
cd /home/admin/NeuralGridSignal
python3 -m neural_grid_signal --once
```

dry-run：

```bash
python3 -m neural_grid_signal --once --dry-run
```

dry-run 会生成策略文件和报告，但不会发送真实 Telegram 消息。

## 常驻调度

默认北京时间 08:00 和 20:00 运行：

```bash
python3 -m neural_grid_signal --schedule
```

修改时间：

```bash
GRID_SIGNAL_SCHEDULE_TIMES=08:00,20:00 python3 -m neural_grid_signal --schedule
```

## 后台运行

如果担心前台 shell 退出，可以使用内置后台脚本。脚本使用 `nohup` 启动常驻调度，PID 写到 `run/grid_signal.pid`，日志写到 `logs/grid_signal.log` 和 `logs/grid_signal.out`。

启动：

```bash
cd /home/admin/NeuralGridSignal
./scripts/start_scheduler.sh
```

查看状态：

```bash
./scripts/status_scheduler.sh
```

停止：

```bash
./scripts/stop_scheduler.sh
```

查看实时日志：

```bash
tail -f logs/grid_signal.log
```

启动后日志会立即写入调度器状态，包括 PID、配置时区、定时点和下一次运行时间。停止脚本发送 SIGTERM 后，进程会写入停止原因，并发送停止通知。

`logs/grid_signal.log` 使用 5 MB 轮转，最多保留 5 个历史文件，避免常驻进程长期运行导致单个日志文件过大。

内置 scheduler 会串行执行扫描任务，并用进程内锁防止同一进程内重复触发重叠执行；如果上一轮任务仍在运行，新触发会跳过并写 warning 日志。cron 方案如果需要同样防重叠，建议配合系统级锁，例如 `flock`。

Telegram、OKX、Binance HTTP 请求会对临时网络错误、429 和 5xx 响应进行最多 3 次指数退避重试。

## cron 方案

如果不希望常驻进程，推荐用 cron：

```cron
0 8,20 * * * cd /home/admin/NeuralGridSignal && /usr/bin/python3 -m neural_grid_signal --once >> logs/grid_signal.log 2>&1
```

注意服务器时区。如果服务器不是北京时间，需要把 cron 时间换算到服务器本地时区，或使用 systemd timer。

## 明天北京时间早晚 8 点各跑一次

如果今天是 2026-05-13，则“明天北京时间早晚 8 点”是：

- 2026-05-14 08:00 Asia/Shanghai
- 2026-05-14 20:00 Asia/Shanghai

可临时使用 `at` 或 cron 指定日期运行，也可以直接启动 `--schedule` 常驻，系统会自动计算下一次 08:00 或 20:00。

## Telegram 内容

启动和停止通知会包含：

- 服务状态：STARTED / STOPPED / ERROR
- timezone
- schedule
- next run
- pid
- stop reason

策略信号通知使用移动端分区格式，包含：

- symbol
- score / confidence / direction
- action
- grid_count
- total_investment
- leverage
- distribution
- direction_bias_ratio
- atr_multiplier
- stop_loss_pct
- daily_loss_limit_pct
- backtest score / hits / skew
- risk_tags
- strategy_file

移动端只需打开 nofx 导入对应 JSON，并核对这些关键参数。

`action` 含义：

- `可导入`：可按低杠杆网格执行。
- `防守观察`：仅建议小资金观察，导入前人工确认区间仍有效。
- `人工复核`：评分不够强，需看报告。
- `等待`：不建议导入。

## 故障处理

没有候选币：

- 检查 OKX 网络是否可访问。
- 降低 `GRID_SIGNAL_MIN_VOLUME_24H` 或 `GRID_SIGNAL_MIN_OI_VALUE`。
- 查看日志中是否所有候选 K 线不足。

Telegram 未发送：

- 检查 `TELEGRAM_BOT_TOKEN_GRID`。
- 检查 `TELEGRAM_CHANNEL_ID_GRID`。
- dry-run 会返回 skipped，不是故障。
- `Bad Request: not enough rights to send text messages to the chat`：bot 已找到目标频道/群，但没有发消息权限。把 bot 加为频道管理员，并授予 Post Messages/发送消息权限。
- `Bad Request: chat not found`：channel id 不对，或 bot 没加入该频道/群。频道可用 `@channelusername` 或 `-100...` ID。

策略文件生成但 nofx 导入异常：

- 检查 `config.strategy_type == "grid_trading"`。
- 检查 `config.coin_source.static_coins[0]` 与 `config.grid_config.symbol` 是否一致。
- 检查 JSON 是否完整。

OpenAI 复核不可用：

- 缺少 `OPEN_AI_ENDPOINT`、`OPEN_AI_MODEL`、`OPEN_AI_API_KEY` 时会自动跳过。
- LLM 只做复核，不负责绕过硬风控。

## 验证

每次改动后运行：

```bash
python3 -m pytest -q
python3 -m compileall neural_grid_signal
python3 -m neural_grid_signal --once --dry-run --limit 5
```

最后一条会访问真实交易所公共行情接口；如果网络不可用，前两条仍应通过。
