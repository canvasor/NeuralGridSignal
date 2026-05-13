from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from neural_grid_signal.config import load_settings
from neural_grid_signal.models import RunResult
from neural_grid_signal.runner import GridSignalRunner
from neural_grid_signal.scheduler import run_forever


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OKX futures AI grid signal assistant")
    parser.add_argument("--once", action="store_true", help="run one scan and exit")
    parser.add_argument("--schedule", action="store_true", help="run continuously at configured Beijing times")
    parser.add_argument("--dry-run", action="store_true", help="do not send Telegram message")
    parser.add_argument("--limit", type=int, default=None, help="candidate count")
    parser.add_argument("--log-level", default="INFO", help="logging level")
    parser.add_argument("--log-file", default="logs/grid_signal.log", help="log file path")
    return parser


def format_run_result(result: RunResult) -> str:
    notification = result.notification
    if notification is None:
        notification_text = "notification=unknown"
    elif notification.sent:
        notification_text = f"notification=sent reason={notification.reason}"
    else:
        notification_text = f"notification=skipped reason={notification.reason}"
    return (
        f"selected={result.selected.symbol} score={result.selected.final_score} "
        f"strategy={result.strategy_path} report={result.report_path} {notification_text}"
    )


async def _run(args: argparse.Namespace) -> None:
    settings = load_settings()
    if args.dry_run:
        settings.dry_run = True
    runner = GridSignalRunner(settings=settings)
    if args.schedule and not args.once:
        await run_forever(lambda: runner.run_once(limit=args.limit), settings.schedule_times, settings.timezone)
        return
    result = await runner.run_once(limit=args.limit)
    print(format_run_result(result))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
