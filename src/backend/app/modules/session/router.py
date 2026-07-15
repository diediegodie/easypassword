from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthError
from app.core.rate_limit import require_rate_limit
from app.infra.database import get_db
from app.modules.session.service import revoke_session, rotate_session

router = APIRouter(
    prefix="/session",
    tags=["session"],
    dependencies=[Depends(require_rate_limit)],
)


class SessionTokenPayload(BaseModel):
    refresh_token: str | None = None


def _refresh_cookie_secure() -> bool:
    return settings.APP_ENV != "development"


def _resolve_refresh_token(
    request: Request, payload: SessionTokenPayload | None
) -> str:
    if payload is not None and payload.refresh_token:
        return payload.refresh_token

    cookie_token = request.cookies.get("refresh_token")
    if cookie_token:
        return cookie_token

    raise AuthError("refresh token required")


@router.post(
    "/refresh",
    responses={
        200: {
            "description": "Refresh token rotated and new access token returned.",
            "content": {
                "application/json": {
                    "example": {"access_token": "<jwt-token>"}
                }
            },
        },
        401: {
            "description": "Authentication failed or reauthentication required.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Reauthentication required",
                        "code": "ReauthenticationRequired",
                    }
                }
            },
        },
    },
)
async def refresh_session(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: SessionTokenPayload | None = None,
) -> dict[str, str]:
    refresh_token = _resolve_refresh_token(request, payload)
    access_token, new_refresh_token = await rotate_session(db, refresh_token)
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=_refresh_cookie_secure(),
        samesite="strict",
        path="/",
    )
    return {"access_token": access_token}


@router.post("/revoke")
async def revoke_session_route(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: SessionTokenPayload | None = None,
) -> dict[str, str]:
    refresh_token = _resolve_refresh_token(request, payload)
    await revoke_session(db, refresh_token)
    response.delete_cookie(key="refresh_token", path="/")
    return {"status": "revoked"}
