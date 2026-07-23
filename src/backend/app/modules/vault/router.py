from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ReplayDetectedError, ValidationError
from app.core.middleware.auth import require_vault_scope
from app.core.config import settings
from app.infra.database import get_db
from app.infra.redis_client import add_replay_blob
from app.modules.session.service import (
    get_current_active_user_and_device,
    get_current_user_and_device,
)
from app.modules.vault.models import Vault
from app.modules.vault.schemas import (
    VaultCreateRequest,
    VaultItemResponse,
    VaultUpdateRequest,
)
from app.modules.vault.utils import format_blob_v1, hash_blob, parse_blob_v1

router = APIRouter(prefix="/vault", tags=["vault"])


@router.get(
    "/",
    response_model=list[VaultItemResponse],
)
async def list_vault(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: dict[str, object] = Depends(require_vault_scope("vault:read")),
) -> list[VaultItemResponse]:
    user_id, _ = await get_current_user_and_device(payload, db)
    result = await db.execute(select(Vault).where(Vault.user_id == user_id))
    items = result.scalars().all()
    response.headers["X-Vault-Blob-Version"] = "1"
    return [
        VaultItemResponse(
            id=str(item.id),
            service_name=item.service_name,
            login_name=item.login_name,
            password_blob=format_blob_v1(item.password_blob),
            notes_blob=(
                format_blob_v1(item.notes_blob) if item.notes_blob is not None else None
            ),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]


@router.post("/", response_model=VaultItemResponse)
async def create_vault(
    request: VaultCreateRequest,
    http_request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: dict[str, object] = Depends(require_vault_scope("vault:write")),
) -> VaultItemResponse:
    user_id, _ = await get_current_user_and_device(payload, db)
    try:
        parsed_password_blob = parse_blob_v1(request.password_blob)
    except ValueError as exc:
        raise ValidationError(
            "malformed or non-base64 blob", code="ERR_INVALID_BLOB"
        ) from exc
    password_hash = hash_blob(parsed_password_blob)
    if not await add_replay_blob(
        user_id=str(user_id),
        blob_hash=password_hash,
        ttl=settings.REPLAY_CACHE_TTL_SECONDS,
    ):
        raise ReplayDetectedError(
            detail="duplicate blob detected within replay window",
            code="ERR_REPLAY_DETECTED",
        )

    notes_blob = None
    if request.notes_blob is not None:
        try:
            notes_blob = parse_blob_v1(request.notes_blob)
        except ValueError as exc:
            raise ValidationError(
                "malformed or non-base64 blob", code="ERR_INVALID_BLOB"
            ) from exc

    vault_item = Vault(
        user_id=user_id,
        service_name=request.service_name,
        login_name=request.login_name,
        password_blob=parsed_password_blob,
        notes_blob=notes_blob,
    )
    db.add(vault_item)
    await db.commit()
    await db.refresh(vault_item)
    response.headers["X-Vault-Blob-Version"] = "1"
    return VaultItemResponse(
        id=str(vault_item.id),
        service_name=vault_item.service_name,
        login_name=vault_item.login_name,
        password_blob=format_blob_v1(vault_item.password_blob),
        notes_blob=(
            format_blob_v1(vault_item.notes_blob)
            if vault_item.notes_blob is not None
            else None
        ),
        created_at=vault_item.created_at,
        updated_at=vault_item.updated_at,
    )


@router.put("/{vault_id}", response_model=VaultItemResponse)
async def update_vault(
    vault_id: str,
    request: VaultUpdateRequest,
    http_request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: dict[str, object] = Depends(require_vault_scope("vault:write")),
) -> VaultItemResponse:
    user_id, _ = await get_current_user_and_device(payload, db)
    try:
        vault_uuid = UUID(vault_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid vault id") from exc

    result = await db.execute(
        select(Vault).where(Vault.id == vault_uuid, Vault.user_id == user_id)
    )
    vault_item = result.scalar_one_or_none()
    if vault_item is None:
        raise HTTPException(status_code=404, detail="vault item not found")

    if request.service_name is not None:
        vault_item.service_name = request.service_name
    if request.login_name is not None:
        vault_item.login_name = request.login_name
    if request.password_blob is not None:
        try:
            parsed_password_blob = parse_blob_v1(request.password_blob)
        except ValueError as exc:
            raise ValidationError(
                "malformed or non-base64 blob", code="ERR_INVALID_BLOB"
            ) from exc
        password_hash = hash_blob(parsed_password_blob)
        if not await add_replay_blob(
            user_id=str(user_id),
            blob_hash=password_hash,
            ttl=settings.REPLAY_CACHE_TTL_SECONDS,
        ):
            raise ReplayDetectedError(
                detail="duplicate blob detected within replay window",
                code="ERR_REPLAY_DETECTED",
            )
        vault_item.password_blob = parsed_password_blob
    if request.notes_blob is not None:
        try:
            vault_item.notes_blob = parse_blob_v1(request.notes_blob)
        except ValueError as exc:
            raise ValidationError(
                "malformed or non-base64 blob", code="ERR_INVALID_BLOB"
            ) from exc

    await db.commit()
    await db.refresh(vault_item)
    response.headers["X-Vault-Blob-Version"] = "1"
    return VaultItemResponse(
        id=str(vault_item.id),
        service_name=vault_item.service_name,
        login_name=vault_item.login_name,
        password_blob=format_blob_v1(vault_item.password_blob),
        notes_blob=(
            format_blob_v1(vault_item.notes_blob)
            if vault_item.notes_blob is not None
            else None
        ),
        created_at=vault_item.created_at,
        updated_at=vault_item.updated_at,
    )


@router.delete("/{vault_id}")
async def delete_vault(
    vault_id: str,
    http_request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: dict[str, object] = Depends(require_vault_scope("vault:write")),
) -> dict[str, str]:
    user_id, _ = await get_current_user_and_device(payload, db)
    try:
        vault_uuid = UUID(vault_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid vault id") from exc

    result = await db.execute(
        select(Vault).where(Vault.id == vault_uuid, Vault.user_id == user_id)
    )
    vault_item = result.scalar_one_or_none()
    if vault_item is None:
        raise HTTPException(status_code=404, detail="vault item not found")

    await db.delete(vault_item)
    await db.commit()
    return {"status": "deleted"}
