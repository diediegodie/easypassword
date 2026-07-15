from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.infra.database import get_db
from app.modules.session.service import get_current_active_user_and_device

router = APIRouter(prefix="/protected", tags=["protected"])


async def require_active_session(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> tuple[str, str]:
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
