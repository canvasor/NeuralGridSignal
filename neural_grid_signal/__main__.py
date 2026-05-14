from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from neural_grid_signal.config import load_settings
from neural_grid_signal.models import NotificationResult, RunResult
from neural_grid_signal.runner import GridSignalRunner
from neural_grid_signal.scheduler import next_run_after, run_forever

logger = logging.getLogger(__name__)

LOG_MAX_BYTES = 5_000_000
LOG_BACKUP_COUNT = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OKX futures AI grid signal assistant")
    parser.add_argument("--once", action="store_true", help="run one scan and exit")
    parser.add_argument("--schedule", action="store_true", help="run continuously at configured Beijing times")
    parser.add_argument("--dry-run", action="store_true", help="do not send Telegram message")
    parser.add_argument("--limit", type=int, default=None, help="candidate count")
    parser.add_argument("--investment", type=float, default=None, help="grid investment in USDT")
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
    strategy_path = result.strategy_path if result.strategy_path is not None else "none"
    return (
        f"outcome={result.outcome} selected={result.selected.symbol} score={result.selected.final_score} "
        f"strategy={strategy_path} report={result.report_path} snapshot={result.snapshot_path} {notification_text}"
    )


def build_log_handlers(log_file: str | Path | None) -> list[logging.Handler]:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_path,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        )
    return handlers


async def _run(args: argparse.Namespace) -> None:
    settings = load_settings()
    if args.dry_run:
        settings.dry_run = True
    if args.investment is not None:
        settings.grid_investment_usdt = args.investment
    runner = GridSignalRunner(settings=settings)
    if args.schedule and not args.once:
        await _run_scheduled(args, settings, runner)
        return
    result = await runner.run_once(limit=args.limit)
    print(format_run_result(result))


def _install_shutdown_handlers(stop_event: asyncio.Event, shutdown_reason: dict[str, str]) -> None:
    loop = asyncio.get_running_loop()

    def request_shutdown(signame: str) -> None:
        if stop_event.is_set():
            return
        shutdown_reason["value"] = signame
        logger.info("scheduler shutdown requested signal=%s", signame)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_shutdown, sig.name)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda _signum, _frame, name=sig.name: request_shutdown(name))


async def _send_scheduler_event(
    notifier: object,
    *,
    event: str,
    schedule_times: tuple[str, ...],
    timezone_name: str,
    next_run_at: datetime | None = None,
    reason: str = "",
) -> NotificationResult | None:
    send_scheduler_event = getattr(notifier, "send_scheduler_event", None)
    if not callable(send_scheduler_event):
        return None
    result = await send_scheduler_event(
        event=event,
        schedule_times=schedule_times,
        timezone_name=timezone_name,
        next_run_at=next_run_at,
        pid=os.getpid(),
        reason=reason,
    )
    if isinstance(result, NotificationResult):
        logger.info("scheduler %s notification sent=%s reason=%s", event, result.sent, result.reason)
        return result
    return None


async def _run_scheduled(args: argparse.Namespace, settings, runner: GridSignalRunner) -> None:
    stop_event = asyncio.Event()
    shutdown_reason = {"value": "normal"}
    _install_shutdown_handlers(stop_event, shutdown_reason)

    next_run_at = next_run_after(datetime.now(settings.timezone), settings.schedule_times, settings.timezone)
    logger.info(
        "scheduler started pid=%s schedule_times=%s timezone=%s next_run_at=%s",
        os.getpid(),
        ",".join(settings.schedule_times),
        settings.timezone_name,
        next_run_at.isoformat(),
    )
    await _send_scheduler_event(
        runner.notifier,
        event="started",
        schedule_times=settings.schedule_times,
        timezone_name=settings.timezone_name,
        next_run_at=next_run_at,
    )
    try:
        await run_forever(
            lambda: runner.run_once(limit=args.limit),
            settings.schedule_times,
            settings.timezone,
            stop_event=stop_event,
        )
    except Exception:
        logger.exception("scheduler crashed")
        await _send_scheduler_event(
            runner.notifier,
            event="error",
            schedule_times=settings.schedule_times,
            timezone_name=settings.timezone_name,
            reason="unexpected exception",
        )
        raise
    finally:
        logger.info("scheduler stopped pid=%s reason=%s", os.getpid(), shutdown_reason["value"])
        await _send_scheduler_event(
            runner.notifier,
            event="stopped",
            schedule_times=settings.schedule_times,
            timezone_name=settings.timezone_name,
            reason=shutdown_reason["value"],
        )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=build_log_handlers(args.log_file),
    )
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
