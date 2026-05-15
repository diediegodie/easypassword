from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.rate_limit import require_rate_limit

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(require_rate_limit)],
)


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}
