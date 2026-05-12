from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Depends, HTTPException, Request

from app.infra.redis_client import get_redis, set_rate_limit

RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60
SENSITIVE_PATH_PREFIXES = (
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/session/refresh",
)

_LOCAL_RATE_LIMITS: dict[str, Deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()

    if request.client is not None and request.client.host:
        return request.client.host

    return "unknown"


def _is_sensitive_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in SENSITIVE_PATH_PREFIXES)


def _allow_local_request(client_ip: str, path: str) -> bool:
    timestamps = _LOCAL_RATE_LIMITS[f"{client_ip}:{path}"]
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS

    while timestamps and timestamps[0] <= cutoff:
        timestamps.popleft()

    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        return False

    timestamps.append(now)
    return True


async def require_rate_limit(
    request: Request,
    _: object = Depends(get_redis),
) -> None:
    if not _is_sensitive_path(request.url.path):
        return

    client_ip = _client_ip(request)
    key = f"rate_limit:{client_ip}:{request.url.path}"

    try:
        allowed = await set_rate_limit(
            key, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS
        )
    except Exception:
        allowed = _allow_local_request(client_ip, request.url.path)

    if not allowed:
        raise HTTPException(status_code=429, detail="too many requests")
