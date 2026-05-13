from __future__ import annotations

import time
import urllib.request
from http.client import RemoteDisconnected
from urllib.error import HTTPError, URLError

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def urlopen_with_retries(
    request: urllib.request.Request,
    *,
    timeout: int,
    attempts: int = 3,
    base_delay_seconds: float = 0.5,
):
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code not in RETRY_STATUS_CODES or attempt >= attempts:
                raise
            time.sleep(base_delay_seconds * (2 ** (attempt - 1)))
        except (RemoteDisconnected, TimeoutError, URLError, OSError):
            if attempt >= attempts:
                raise
            time.sleep(base_delay_seconds * (2 ** (attempt - 1)))

    raise RuntimeError("unreachable retry state")
