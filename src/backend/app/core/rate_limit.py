from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Annotated, Deque

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, hash_refresh_token
from app.infra.database import get_db
from app.infra.redis_client import get_redis, set_rate_limit
from app.infra.redis_keys import RATE_LIMIT_KEY
from app.modules.session.models import Session as SessionModel

RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60
SENSITIVE_PATH_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/session/",
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


def _authorization_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization")
    if not authorization:
        return None

    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None

    return value.strip()


async def _resolve_user_from_refresh_token(
    refresh_token: str, db: AsyncSession
) -> str | None:
    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(
        sa.select(SessionModel.user_id).where(
            sa.or_(
                SessionModel.refresh_token_hash == token_hash,
                SessionModel.previous_token_hash == token_hash,
            )
        )
    )
    user_id = result.scalar_one_or_none()
    return str(user_id) if user_id is not None else None


async def _extract_user_scope(request: Request, db: AsyncSession) -> str:
    token = _authorization_bearer_token(request)
    if token:
        try:
            payload = decode_access_token(token)
            subject = payload.get("sub")
            if isinstance(subject, str) and subject.strip():
                return subject.strip()
        except Exception:
            pass

    refresh_token = request.cookies.get("refresh_token")
    if isinstance(refresh_token, str) and refresh_token.strip():
        user_from_cookie = await _resolve_user_from_refresh_token(refresh_token, db)
        if user_from_cookie is not None:
            return user_from_cookie

    try:
        payload = await request.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        payload_refresh_token = payload.get("refresh_token")
        if isinstance(payload_refresh_token, str) and payload_refresh_token.strip():
            user_from_payload = await _resolve_user_from_refresh_token(
                payload_refresh_token, db
            )
            if user_from_payload is not None:
                return user_from_payload

        email = payload.get("email")
        if isinstance(email, str) and email.strip():
            return email.strip().lower()

    return "anonymous"


def _allow_local_request(client_ip: str, user_scope: str, path: str) -> bool:
    timestamps = _LOCAL_RATE_LIMITS[f"{client_ip}:{user_scope}:{path}"]
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS

    while timestamps and timestamps[0] <= cutoff:
        timestamps.popleft()

    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        return False

    timestamps.append(now)
    return True


async def get_db_session(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncSession:
    return db


async def require_rate_limit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: object = Depends(get_redis),
) -> None:
    if not _is_sensitive_path(request.url.path):
        return

    client_ip = _client_ip(request)
    user_scope = await _extract_user_scope(request, db)
    key = RATE_LIMIT_KEY.format(
        client_ip=client_ip,
        user=user_scope,
        path=request.url.path,
    )

    try:
        allowed = await set_rate_limit(
            key, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS
        )
    except Exception:
        allowed = _allow_local_request(client_ip, user_scope, request.url.path)

    if not allowed:
        raise HTTPException(status_code=429, detail="too many requests")
