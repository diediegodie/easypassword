from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.infra.database import get_db
from app.modules.session.service import (
    get_current_active_user_and_device,
    get_current_user_and_device,
)

router = APIRouter(prefix="/protected", tags=["protected"])

get_db_dependency = Depends(get_db)


async def require_active_session(
    request: Request,
    authorization: str | None = Header(None),
    db: AsyncSession = get_db_dependency,
) -> tuple[UUID, UUID]:
    if hasattr(request.state, "current_user_payload"):
        return await get_current_user_and_device(request.state.current_user_payload, db)

    if not authorization:
        raise AuthError("invalid or expired token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("invalid or expired token")

    return await get_current_active_user_and_device(token.strip(), db)


@router.get("/test")
async def test_protected(
    _: tuple[str, str] = Depends(require_active_session),
) -> dict[str, str]:
    return {"status": "ok"}
