# EasyPassword

> A passwordless, mobile-first password manager built around passkeys, client-side encryption, and a minimal-trust backend.

EasyPassword is a V1 product focused on a simple idea: make password management feel like unlocking a modern device, not managing another traditional login. The app uses WebAuthn/passkeys for authentication, encrypts sensitive data on the device before it ever reaches the backend, and keeps the server responsible only for what it truly needs to store and validate.

## What EasyPassword Is

EasyPassword is a Progressive Web App designed for daily use on mobile devices, starting with iPhone. The product is intentionally narrow in scope so it can stay secure, predictable, and easy to trust over time.

It is built for a world where:

- the user signs in without a traditional password
- the device itself becomes the primary trusted entry point
- sensitive vault data never needs to be decrypted by the backend
- the session layer stays simple and anchored in PostgreSQL
- offline functionality is intentionally out of scope for V1

## The Product in One Sentence

EasyPassword is a password manager that combines passkey-based authentication, client-side encryption, and a single-device session model to reduce friction without expanding trust in the backend.

## Core Experience

### First access

On first use, the user registers a device with WebAuthn/passkeys. That step creates the trust relationship between the account and the device, and it initializes the local key needed to protect the vault.

### Daily access

Later, the user returns with the same device and unlocks the app using the operating system’s native verification flow, such as Face ID, Touch ID, PIN, or the equivalent supported method.

### Vault protection

Passwords and sensitive notes are encrypted on the client using the Web Crypto API before any data is sent to the backend. The backend stores encrypted blobs and the minimal metadata needed to manage the vault.

### Session behavior

Sessions are intentionally short-lived and predictable:

- access tokens are short-lived
- refresh tokens are opaque and rotated on every renewal
- refresh token reuse triggers immediate revocation
- Redis is used only for ephemeral data such as challenges and rate limiting
- PostgreSQL remains the source of truth for sessions

## Design Principles

EasyPassword is shaped by a few strict product principles:

- **Passwordless by default**: no traditional password flow in V1.
- **Single-device trust**: one active user, one active device.
- **Client-side secrecy**: the backend never receives the decryption key.
- **Minimal-trust server**: the backend validates, persists, and coordinates, but does not decrypt vault content.
- **Mobile-first delivery**: the app is designed to feel natural on iPhone and other modern mobile environments.
- **No offline functional mode**: the app depends on an active backend connection to open and function.

## Why This Exists

Most password managers add layers of abstraction that can make the experience heavier than it needs to be. EasyPassword explores a different balance:

- fewer moving parts for the user
- stronger alignment with modern device security
- less backend trust surface
- a clearer path to secure daily use

The goal is not to be everything at once. The goal is to make one narrow product category feel modern, trustworthy, and sustainable.

## Official V1 Scope

V1 is deliberately constrained.

It includes:

- WebAuthn/passkey registration and login
- one active device per account
- encrypted vault data stored in PostgreSQL
- refresh token rotation and reuse detection
- mobile-first PWA delivery
- Redis for ephemeral challenge and rate-limit support

It excludes:

- account recovery
- device migration
- multi-device support
- offline functional use
- backend-side decryption of vault content

## Technical Shape

```text
User Device
    ↓
Angular PWA
    ↓
WebAuthn + Web Crypto API
    ↓
FastAPI
    ↓
PostgreSQL
```

### Stack overview

- **Frontend**: Angular, PWA, WebAuthn API, Web Crypto API, HttpClient, Signals
- **Backend**: FastAPI, SQLAlchemy, Alembic, Pydantic, PostgreSQL, Redis, cryptography, py_webauthn, Uvicorn
- **Infrastructure**: Docker, Docker Compose, GitHub Actions, Render

## Data Model

EasyPassword centers around four persistent domains:

- **users**: account identity and status
- **devices**: the registered WebAuthn device and its credential metadata
- **vaults**: encrypted password and note entries
- **sessions**: persistent refresh-token-backed session state in PostgreSQL

## Security Posture

The product is built to reduce trust in the backend rather than increase it.

That means:

- the refresh token is stored only as a hash
- session rotation is mandatory
- token reuse causes immediate revocation
- cookies are HttpOnly and Secure
- Redis is limited to short-lived ephemeral concerns
- vault content remains encrypted end to end on the client

## Vision

EasyPassword is meant to feel like a calm, modern security product: fast to unlock, hard to misuse, and careful about where trust lives.

It should be small enough to stay understandable, but strong enough to serve as a real password manager foundation for years.

## Testing

### Structure
- `tests/unit/` - Unit tests (fast, no external dependencies)
- `tests/integration/` - Integration tests (require Docker with PostgreSQL)

### Running tests

**Unit tests only (recommended for fast development):**
```bash
make test-unit
# or
RUN_INTEGRATION=0 pytest tests/unit/
```

**Full test suite (includes integration):**
```bash
make test-all
# or
cd src/infra/docker && docker-compose up -d
cd ../backend && RUN_INTEGRATION=1 pytest
cd ../infra/docker && docker-compose down
```

**CI/CD**
In the pipeline, run `RUN_INTEGRATION=1 pytest` with `docker-compose up`.
