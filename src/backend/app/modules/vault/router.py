from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.infra.database import get_db
from app.modules.session.service import get_current_active_user_and_device
from app.modules.vault.models import Vault
from app.modules.vault.schemas import (
    VaultCreateRequest,
    VaultItemResponse,
    VaultUpdateRequest,
)

router = APIRouter(prefix="/vault", tags=["vault"])


@router.get("/", response_model=list[VaultItemResponse])
async def list_vault(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[VaultItemResponse]:
    authorization = request.headers.get("authorization")
    if not authorization:
        raise AuthError("invalid or expired token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("invalid or expired token")

    user_id, _ = await get_current_active_user_and_device(token.strip(), db)
    result = await db.execute(select(Vault).where(Vault.user_id == user_id))
    items = result.scalars().all()
    return [
        VaultItemResponse(
            id=str(item.id),
            service_name=item.service_name,
            login_name=item.login_name,
            password_blob=item.password_blob.decode("utf-8"),
            notes_blob=(
                item.notes_blob.decode("utf-8") if item.notes_blob is not None else None
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
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VaultItemResponse:
    authorization = http_request.headers.get("authorization")
    if not authorization:
        raise AuthError("invalid or expired token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("invalid or expired token")

    user_id, _ = await get_current_active_user_and_device(token.strip(), db)
    vault_item = Vault(
        user_id=user_id,
        service_name=request.service_name,
        login_name=request.login_name,
        password_blob=request.password_blob.encode("utf-8"),
        notes_blob=(
            request.notes_blob.encode("utf-8")
            if request.notes_blob is not None
            else None
        ),
    )
    db.add(vault_item)
    await db.commit()
    await db.refresh(vault_item)
    return VaultItemResponse(
        id=str(vault_item.id),
        service_name=vault_item.service_name,
        login_name=vault_item.login_name,
        password_blob=vault_item.password_blob.decode("utf-8"),
        notes_blob=(
            vault_item.notes_blob.decode("utf-8")
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
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VaultItemResponse:
    authorization = http_request.headers.get("authorization")
    if not authorization:
        raise AuthError("invalid or expired token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("invalid or expired token")

    user_id, _ = await get_current_active_user_and_device(token.strip(), db)
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
        vault_item.password_blob = request.password_blob.encode("utf-8")
    if request.notes_blob is not None:
        vault_item.notes_blob = request.notes_blob.encode("utf-8")

    await db.commit()
    await db.refresh(vault_item)
    return VaultItemResponse(
        id=str(vault_item.id),
        service_name=vault_item.service_name,
        login_name=vault_item.login_name,
        password_blob=vault_item.password_blob.decode("utf-8"),
        notes_blob=(
            vault_item.notes_blob.decode("utf-8")
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
) -> dict[str, str]:
    authorization = http_request.headers.get("authorization")
    if not authorization:
        raise AuthError("invalid or expired token")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("invalid or expired token")

    user_id, _ = await get_current_active_user_and_device(token.strip(), db)
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
