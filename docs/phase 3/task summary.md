# Phase 3.1 Task Summary

## Canonical API Contract (normative) [✓]

- Added contract-aligned blob validation and replay protection for vault API payloads.
- Implemented `parse_blob_v1`, `format_blob_v1`, and `hash_blob` utilities in `src/backend/app/modules/vault/utils.py`.
- Added Redis-backed replay blob cache support in `src/backend/app/infra/redis_client.py` and key pattern in `src/backend/app/infra/redis_keys.py`.
- Hardened `src/backend/app/modules/vault/schemas.py` with `extra="forbid"`, suspicious key rejection, and contract-specific request validation.
- Added FastAPI validation error mapping in `src/backend/app/core/errors.py` for canonical codes: `ERR_EXTRA_FIELDS`, `ERR_SUSPICIOUS_KEY`, `ERR_INVALID_BLOB`, `ERR_BLOB_TOO_LARGE`, `ERR_UNSUPPORTED_BLOB_VERSION`, and `ERR_REPLAY_DETECTED`.
- Updated `src/backend/app/modules/vault/router.py` to store blobs as raw bytes, validate incoming base64 `blob_v1`, reject replayed blobs, and emit `X-Vault-Blob-Version: 1`.

---

## Authentication and Authorization (normative) [✓]

- Implemented JWTAuthMiddleware in `app/core/middleware/auth.py` with scope enforcement (`require_vault_scope`).
- Added 6 authentication/authorization counters in `app/core/metrics.py`.
- Updated `app/modules/vault/router.py` with 4 endpoints protected by `require_vault_scope`.
- Added Redis client context manager in `app/infra/redis_client.py` for revocation checks.
- Defined canonical error codes: `ERR_UNAUTHORIZED`, `ERR_INVALID_TOKEN`, `ERR_TOKEN_REVOKED`.
- All 5 integration tests in `tests/unit/test_auth.py` now pass with runtime RSA key generation (no hardcoded secrets).

---

