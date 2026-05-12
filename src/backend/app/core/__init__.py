"""Core utilities for EasyPassword."""

from app.core.config import Settings, settings
from app.core.errors import (
    AuthError,
    ConflictError,
    EasyPasswordError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
    register_exception_handlers,
)
from app.core.logging import configure_logging
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_refresh_token,
)

__all__ = [
    "AuthError",
    "ConflictError",
    "EasyPasswordError",
    "ForbiddenError",
    "NotFoundError",
    "Settings",
    "ValidationError",
    "configure_logging",
    "create_access_token",
    "decode_access_token",
    "generate_refresh_token",
    "hash_refresh_token",
    "register_exception_handlers",
    "settings",
    "verify_refresh_token",
]
