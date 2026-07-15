from __future__ import annotations

from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.protected.router import router as protected_router
from app.modules.session.router import router as session_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(session_router)
api_router.include_router(auth_router)
api_router.include_router(protected_router)

# Phase 2 will add auth_router here.
# Phase 3 will add vault_router here.
