from __future__ import annotations

from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.errors import EasyPasswordError
from app.modules.session.service import validate_session_activity

PUBLIC_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/",
    "/api/v1/session/refresh",
    "/api/v1/session/revoke",
)


def _authorization_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization")
    if not authorization:
        return None

    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None

    return value.strip()


def _should_validate_request(request: Request) -> bool:
    if request.url.path is None:
        return False

    return not any(
        request.url.path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES
    )


class SessionActivityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _should_validate_request(request):
            token = _authorization_bearer_token(request)
            if token is not None:
                session_factory = getattr(request.app.state, "db_session_factory", None)
                if session_factory is not None:
                    async with session_factory() as db:
                        try:
                            payload = await validate_session_activity(db, token)
                            request.state.current_user_payload = payload
                        except EasyPasswordError as exc:
                            content = {"detail": exc.detail}
                            code = getattr(exc, "code", None)
                            if code is not None:
                                content["code"] = code
                            return JSONResponse(
                                status_code=exc.status_code, content=content
                            )
        return await call_next(request)
