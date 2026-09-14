"""Validation and process-wide limits for expensive public endpoints."""
from collections import deque
from datetime import date, datetime
from threading import Lock
from time import monotonic
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Query

CURRENT_YEAR = datetime.now(ZoneInfo("Asia/Seoul")).year
Season = Annotated[int, Query(ge=1982, le=CURRENT_YEAR)]
_requests = deque()
_lock = Lock()


def limit_expensive_requests():
    # Global limit also covers requests through a proxy; forwarded IPs are untrusted.
    now = monotonic()
    with _lock:
        while _requests and _requests[0] <= now - 60:
            _requests.popleft()
        if len(_requests) >= 60:
            raise HTTPException(429, "Too many requests", headers={"Retry-After": "60"})
        _requests.append(now)


def validated_date(value: str | None) -> str:
    if value is None:
        return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value or not 1982 <= parsed.year <= CURRENT_YEAR:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "date must be YYYY-MM-DD within supported seasons") from None
    return value
