from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.core.rate_limit import require_rate_limit
from app.core.security import refresh_cookie_secure
from app.infra.database import get_db
from app.modules.session.models import Session as SessionModel
from app.modules.session.service import (
    get_current_user_and_device,
    revoke_session,
    rotate_session,
)

router = APIRouter(
    prefix="/session",
    tags=["session"],
    dependencies=[Depends(require_rate_limit)],
)


class SessionTokenPayload(BaseModel):
    refresh_token: str | None = None


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
                "application/json": {"example": {"access_token": "<jwt-token>"}}
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
        secure=refresh_cookie_secure(),
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


class SessionListItem(BaseModel):
    session_id: str
    device_id: str
    issued_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime


@router.get("/")
async def list_sessions(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SessionListItem]:
    authorization = request.headers.get("authorization")
    if not authorization:
        raise AuthError("invalid or expired token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("invalid or expired token")

    user_id, _ = await get_current_user_and_device(token.strip(), db)
    result = await db.execute(
        select(SessionModel).where(SessionModel.user_id == user_id)
    )
    sessions = result.scalars().all()
    return [
        SessionListItem(
            session_id=str(session.id),
            device_id=str(session.device_id),
            issued_at=session.issued_at,
            last_activity_at=session.last_activity_at,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
            created_at=session.created_at,
        )
        for session in sessions
    ]
