from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


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
) -> None:
    now_fn = now_fn or (lambda: datetime.now(tz))
    while True:
        run_at = next_run_after(now_fn(), schedule_times, tz)
        sleep_seconds = max(0.0, (run_at - now_fn().astimezone(tz)).total_seconds())
        await asyncio.sleep(sleep_seconds)
        await job()
