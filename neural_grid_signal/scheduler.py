from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def next_run_after(now: datetime, schedule_times: tuple[str, ...], tz: ZoneInfo) -> datetime:
    local_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    candidates = []
    for item in schedule_times:
        hour, minute = [int(part) for part in item.split(":", 1)]
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > local_now:
            candidates.append(candidate)
    if candidates:
        return min(candidates)
    hour, minute = [int(part) for part in schedule_times[0].split(":", 1)]
    tomorrow = local_now + timedelta(days=1)
    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)


async def run_forever(
    job: Callable[[], Awaitable[object]],
    schedule_times: tuple[str, ...],
    tz: ZoneInfo,
    *,
    now_fn: Callable[[], datetime] | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    now_fn = now_fn or (lambda: datetime.now(tz))
    while True:
        run_at = next_run_after(now_fn(), schedule_times, tz)
        sleep_seconds = max(0.0, (run_at - now_fn().astimezone(tz)).total_seconds())
        logger.info("scheduler waiting next_run_at=%s sleep_seconds=%.0f", run_at.isoformat(), sleep_seconds)
        if stop_event is not None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
                logger.info("scheduler stop requested before next run")
                return
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(sleep_seconds)
        logger.info("scheduler job started run_at=%s", run_at.isoformat())
        await job()
        logger.info("scheduler job finished run_at=%s", run_at.isoformat())
