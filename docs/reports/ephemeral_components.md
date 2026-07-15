# Ephemeral Components (Phase 1.4)

This document describes the Redis-backed ephemeral components used in V1: WebAuthn challenge storage and basic rate limiting.

## WebAuthn challenge TTL

- Purpose: store ephemeral WebAuthn challenges issued to clients during registration/authentication flows.
- Default TTL: `WEBAUTHN_CHALLENGE_TTL_SECONDS = 90` seconds.

## Redis key naming

- Challenges are stored with the key prefix defined in `app.infra.redis_keys` as:

  `WEBAUTHN_CHALLENGE_KEY = "webauthn:challenge:{}"`

  The rate-limit key pattern is defined as:

  `RATE_LIMIT_KEY = "rate_limit:{client_ip}:{user}:{path}"`

  These constants centralize patterns without changing the literal key values used in production.

## Challenge storage behavior

- `set_challenge(challenge_id, challenge_bytes)` stores the challenge using `SETEX` with the challenge TTL plus the configured clock-skew tolerance so the Redis entry matches server-side expiration checks.
- `get_challenge(challenge_id)` attempts to atomically consume the challenge using `GETDEL` when available; if `GETDEL` is not available, it falls back to `GET` followed by `DEL`.

## Rate limiting

- Implementation: a small Lua script run via `EVAL` that increments a per-client-per-user-per-path counter and sets an expiration on first increment.
- Script behavior (in `redis_client.set_rate_limit`):
  - `INCR` the key.
  - If the value is `1` (first hit), `EXPIRE` the key to the configured window.
  - Return the current counter value; the caller decides whether the request is allowed.

- Local fallback: when Redis is unavailable, a memory-backed sliding window is used per `(client_ip, user, path)`.
  - Config constants:
    - `RATE_LIMIT_REQUESTS` (default: `10`)
    - `RATE_LIMIT_WINDOW_SECONDS` (default: `60`)

- Sensitive paths covered by default:
  - `/api/v1/auth/` (covers `/api/v1/auth/register`, `/api/v1/auth/login`, and future auth endpoints)
  - `/api/v1/session/` (covers `/api/v1/session/refresh`, `/api/v1/session/revoke`, etc.)

- User scope resolution order for limiter keys:
  - access token subject (`sub`) when a valid Bearer token is present
  - user resolved from refresh token when available
  - normalized email from auth payloads when present
  - `anonymous` fallback when user scope cannot be derived

## Developer integration note

- The `require_rate_limit` dependency must be added to routers that expose sensitive endpoints. Example pattern (used for session router):

  `router = APIRouter(prefix="/session", tags=["session"], dependencies=[Depends(require_rate_limit)])`

- The `auth` router is not yet implemented in Phase 1. If/when added, ensure it includes `dependencies=[Depends(require_rate_limit)]` at router creation time.

## Migration note

- Do not change existing production Redis key names without a data migration. The new `redis_keys.py` centralizes patterns only and preserves current literal key formats.

## Tests

- New tests live in `src/backend/tests/`:
  - `test_webauthn_challenge.py` — verifies TTL usage and `GETDEL` fallback behavior.
  - `test_rate_limit.py` — verifies Redis-based `set_rate_limit` behavior and the local fallback blocking logic.

- Run tests locally (from the repository root):

```bash
pytest src/backend/tests -q
```

- Tests are written to mock Redis and do not require a running Redis instance.
