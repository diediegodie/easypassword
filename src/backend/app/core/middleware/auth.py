from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import settings
from app.core.errors import ERR_INVALID_TOKEN, ERR_TOKEN_REVOKED, ERR_UNAUTHORIZED
from app.core.metrics import (
    vault_auth_revocation_checks_total,
    vault_auth_revocation_hits_total,
    vault_auth_revocation_misses_total,
    vault_auth_token_expiry_failures_total,
    vault_auth_token_scope_failures_total,
    vault_auth_token_validations_total,
)
from app.infra.redis_client import _redis_client_context

security = HTTPBearer()
logger = logging.getLogger(__name__)


class JWTAuthMiddleware:
    def __init__(self) -> None:
        self.key = self._load_public_key()

    def _load_public_key(self) -> str:
        if settings.JWT_PUBLIC_KEY:
            if settings.JWT_PUBLIC_KEY.startswith("http"):
                raise NotImplementedError("JWKS endpoint fetching not implemented yet")
            public_key_path = Path(settings.JWT_PUBLIC_KEY)
            if not public_key_path.exists():
                raise RuntimeError(
                    f"Public key file not found at {settings.JWT_PUBLIC_KEY}"
                )
            return public_key_path.read_text()
        return settings.SECRET_KEY

    async def _is_token_revoked(self, token: str, jti: str) -> bool:
        vault_auth_revocation_checks_total.inc()

        if settings.REVOCATION_LIST_BACKEND == "redis":
            async with _redis_client_context() as redis:
                if redis is None:
                    vault_auth_revocation_misses_total.inc()
                    return False
                revoked = await redis.get(f"revoked:jti:{jti}")
            if revoked is not None:
                vault_auth_revocation_hits_total.inc()
                return True
            vault_auth_revocation_misses_total.inc()
            return False

        if settings.REVOCATION_LIST_BACKEND == "introspection_endpoint":
            if not settings.INTROSPECTION_ENDPOINT:
                vault_auth_revocation_misses_total.inc()
                return False
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    settings.INTROSPECTION_ENDPOINT,
                    data={"token": token},
                )
            if response.status_code != 200:
                raise ERR_INVALID_TOKEN()
            if response.json().get("active") is False:
                vault_auth_revocation_hits_total.inc()
                return True
            vault_auth_revocation_misses_total.inc()
            return False

        vault_auth_revocation_misses_total.inc()
        return False

    async def __call__(self, request: Request) -> Dict[str, Any]:
        try:
            credentials: Optional[HTTPAuthorizationCredentials] = await security(
                request
            )
        except HTTPException:
            vault_auth_token_validations_total.labels(status="failure").inc()
            raise ERR_UNAUTHORIZED() from None

        if credentials is None:
            vault_auth_token_validations_total.labels(status="failure").inc()
            raise ERR_UNAUTHORIZED()

        token = credentials.credentials
        if not token:
            vault_auth_token_validations_total.labels(status="failure").inc()
            raise ERR_UNAUTHORIZED()

        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if not algorithm:
                raise JWTError("No algorithm specified in token header")
        except JWTError:
            vault_auth_token_validations_total.labels(status="failure").inc()
            raise ERR_INVALID_TOKEN() from None

        try:
            payload = jwt.decode(
                token,
                self.key,
                algorithms=[algorithm],
                options={"verify_aud": False},
            )

            if not isinstance(payload, dict):
                raise JWTError("Token payload must be an object")

            sub = payload.get("sub")
            exp = payload.get("exp")
            iat = payload.get("iat")
            scope = payload.get("scope")
            jti = payload.get("jti")

            if not isinstance(sub, str) or not sub.strip():
                raise JWTError("Missing 'sub' claim")
            if not isinstance(exp, (int, float)):
                raise JWTError("Missing 'exp' claim")
            if not isinstance(iat, (int, float)):
                raise JWTError("Missing 'iat' claim")
            if not isinstance(scope, (str, list, tuple)):
                raise JWTError("Missing 'scope' claim")
            if not isinstance(jti, str) or not jti.strip():
                raise JWTError("Missing 'jti' claim")

            now = time.time()
            if iat > now + settings.CLOCK_SKEW_TOLERANCE_SECONDS:
                raise JWTError("Token iat is in the future")

            if exp < now:
                vault_auth_token_validations_total.labels(status="failure").inc()
                vault_auth_token_expiry_failures_total.inc()
                raise ExpiredSignatureError("Token has expired")

            if await self._is_token_revoked(token, jti):
                raise ERR_TOKEN_REVOKED()

            vault_auth_token_validations_total.labels(status="success").inc()
            return {"payload": payload, "token": token}

        except ExpiredSignatureError:
            vault_auth_token_validations_total.labels(status="failure").inc()
            vault_auth_token_expiry_failures_total.inc()
            raise ERR_UNAUTHORIZED() from None
        except ERR_TOKEN_REVOKED:
            raise
        except JWTError:
            vault_auth_token_validations_total.labels(status="failure").inc()
            raise ERR_INVALID_TOKEN() from None
        except Exception as exc:
            logger.error("Unexpected error during JWT validation: %s", exc)
            vault_auth_token_validations_total.labels(status="failure").inc()
            raise ERR_INVALID_TOKEN() from None


def require_vault_scope(required_scope: str):
    async def dependency(request: Request) -> Dict[str, Any]:
        auth_context = await JWTAuthMiddleware()(request)
        payload = auth_context["payload"]
        scope_claim = payload.get("scope")

        if isinstance(scope_claim, str):
            scopes = scope_claim.split()
        elif isinstance(scope_claim, (list, tuple)):
            scopes = [str(item) for item in scope_claim]
        else:
            vault_auth_token_validations_total.labels(status="failure").inc()
            vault_auth_token_scope_failures_total.inc()
            raise ERR_UNAUTHORIZED()

        if required_scope not in scopes:
            vault_auth_token_validations_total.labels(status="failure").inc()
            vault_auth_token_scope_failures_total.inc()
            raise ERR_UNAUTHORIZED()

        return payload

    return dependency
