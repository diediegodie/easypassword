# EasyPassword — Official Product Document (V1)

Status: Frozen for V1 implementation

This document is the single source of truth for the V1 of the product.

## Product Objective

Build a web/mobile application in PWA format for password management with a focus on:

- passwordless authentication with WebAuthn/passkeys
- simple use after the first device registration
- end-to-end encryption on the client
- minimal trust architecture on the backend
- mobile-first experience, starting with iPhone
- primary backend in Python

## V1 Scope and Direction

V1 is intentionally limited to maximize reliability, security, and delivery predictability.

V1 scope rules:

- one active user at a time on a single device
- no account recovery flow in V1
- no device migration in V1
- no traditional password
- no reading of sensitive content on the backend
- no multiple frontend stacks

## High-Level Architecture

```
User Device
        ↓
PWA Angular
        ↓
WebAuthn + Web Crypto API
        ↓
FastAPI
        ↓
PostgreSQL
```

## Official V1 Stack

### Frontend

| Technology | Function |
| --- | --- |
| Angular | Main interface |
| Angular CLI | Build and tooling |
| PWA | Installation and use as an app |
| WebAuthn API | Authentication with passkeys |
| Web Crypto API | Client-side encryption |
| HttpClient | Standard HTTP communication |
| Signals | Local state and reactivity |

### Backend

| Technology | Function |
| --- | --- |
| Python | Main language |
| FastAPI | Main API |
| SQLAlchemy | ORM |
| Alembic | Migrations |
| Pydantic | Data validation |
| PostgreSQL | Persistent source of truth |
| Redis | Short-lived ephemeral data |
| cryptography | Support cryptographic operations |
| py_webauthn | WebAuthn credential validation |
| Uvicorn | ASGI server |

### Infrastructure

| Technology | Function |
| --- | --- |
| Docker | Containerization |
| Docker Compose | Local environment |
| Render | Deployment |
| GitHub | Repository |
| GitHub Actions | CI/CD |

## Authentication Model

### First login and device registration

On first access, the user authenticates the device with WebAuthn/passkeys. The device's operating system may use Face ID, Touch ID, PIN, or the equivalent platform-supported method to confirm the user's presence and identity.

During this first login:

- the WebAuthn credential is created and associated with the user
- the device is registered as the active device
- the vault's local key is created on the device itself
- the initial access unlocks the account session

### Daily access

After the first login, the user accesses the app using the operating system's verification via WebAuthn. In practice, this means the device requests biometric confirmation or the device's PIN to grant access.

The app does not treat biometrics as a password. It simply requests authentication from the device's native authenticator.

### Single-device policy

In V1, the account is linked to only one active device.

- if the user removes the app's local data, the device loses the link
- if the device is replaced, the old registration cannot be reused in V1
- simultaneous login on multiple devices is not allowed

## Encryption Model

### Principles

- the Master Key is generated on the device itself
- sensitive data is encrypted on the client before reaching the backend
- the backend stores only encrypted blobs and minimal metadata
- the backend must never have access to the key that decrypts the vault data

### Encryption flow

```
Real password or sensitive content
        ↓
Local encryption with Web Crypto API
        ↓
Encrypted blob
        ↓
API
        ↓
PostgreSQL
```

### Technical rules

- use AES-GCM for vault data
- generate a unique IV/nonce for each cryptographic operation
- use `crypto.getRandomValues()` for secure random value generation
- never reuse IV with the same key
- store only what is necessary to restore local encryption on the device itself

## Data Structure

### users

- id
- email
- account_status
- created_at
- updated_at

### devices

- id
- user_id
- credential_id
- public_key
- device_name
- last_login_at
- created_at

### vaults

- id
- user_id
- service_name
- login_name
- password_blob
- notes_blob
- created_at
- updated_at

### sessions

- id
- user_id
- device_id
- refresh_token_hash
- issued_at
- expires_at
- last_activity_at
- revoked_at
- created_at

## Session Policy

Session behavior must be simple and predictable:

- PostgreSQL is the source of truth for persistent sessions
- Redis is used only for challenges, rate limits, and short expiration
- Rate limiting on sensitive endpoints must include both client IP and user scope
- the backend uses a short-lived JWT access token and an opaque refresh token
- the refresh token must be stored only as a hash in the database
- Redis is not a session authority; it does not replace persistent registration in PostgreSQL
- session cookies must be `HttpOnly` and `Secure`
- expiration and revocation must be centrally controlled on the backend

V1 closed parameters:

- WebAuthn challenge TTL: 90 seconds
- JWT access token validity: 5 minutes
- refresh token validity: 7 days
- refresh token rotation: mandatory on each session renewal
- refresh token reuse detection: immediately revoke the active device session
- inactivity window to require new WebAuthn authentication: 60 seconds
- clock skew tolerance between client and server: 120 seconds

## V1 Features

### Authentication

- passwordless registration with WebAuthn
- login with passkeys and operating system verification
- logout
- session renewal
- challenge expiration

### Vault

- CRUD for passwords
- quick password copy
- item listing with on-demand loading

### Security

- AES-GCM on the client
- WebAuthn for authentication
- short-lived JWT access token + opaque refresh token with hash persisted on the backend
- CSP, rate limit (by IP + user on sensitive endpoints), CSRF when applicable, and mandatory HTTPS

### Mobile/PWA

- custom splash screen and icon
- standalone mode
- no offline functional support in V1

## Offline Behavior

V1 offline mode must follow these rules:

- the app depends on an active connection to the backend to open and function
- without an internet connection, the user cannot access the vault
- creation, editing, deletion, and reading of data require an online connection
- the PWA service worker, if it exists, may only optimize asset loading; it does not enable offline functional use
- there is no offline sync queue in V1

## V1 Support Matrix

Primary support scope:

- main target device: iPhone X
- target operating system: iOS 16.7.x
- target browser: Safari iOS and standalone PWA mode on the same WebKit engine

Secondary scope:

- other devices may work due to compatibility but are outside the V1 support commitment
- there will be no architectural adaptations for Android, desktop, or multiple browsers in this phase

## UI and State Strategy

### Frontend

- use Angular as the only frontend stack in V1
- use HttpClient as the standard communication layer with the API
- maintain Signals for local state and component sharing

### Consistency rule

If any future feature requires another frontend technology, it will only be included in a later phase with explicit justification. V1 must not mix two HTTP clients or two competing patterns for the same layer.

## WebAuthn Behavior

Implementation rules:

- the app must rely on the device's native authenticator verification
- internal biometric changes may remain valid if the system authenticator continues to accept the credential
- the system must treat authentication failures as authenticator verification failures, not cryptographic failures
- the frontend must alert about time discrepancies but cannot force synchronization of the operating system clock

## Error Handling

- expired challenge requires a new challenge
- expired session requires new WebAuthn login
- loss of local storage invalidates the device in V1
- network failures must be handled without losing the local cryptographic state

## Quality and Testing

Mandatory development rule:

- every feature must have relevant tests
- CI must execute validations before merge
- each layer must be testable in isolation
- contracts between frontend and backend must be stable and documented

## V1 Delivery Plan

### Phase 1 — Foundational

- create Angular base
- create FastAPI base
- configure PostgreSQL, migrations, and Docker
- define API contracts

### Phase 2 — Authentication

- register WebAuthn credentials
- validate challenge and login
- create session flow

### Phase 3 — Local Encryption

- generate Master Key on the device
- encrypt and decrypt data on the client
- persist encrypted blobs

### Phase 4 — Vault

- vault CRUD
- optimized listing
- quick password copy

### Phase 5 — PWA

- manifest
- service worker
- standalone installation

### Phase 6 — Hardening

- CSP
- rate limit
- auditing
- security review

### Phase 7 — Production

- deploy on Render
- basic observability
- final validation in a real environment

## Out of Scope Items (V2)

The following capabilities are out of V1 and should be planned later:

- account recovery via email
- device migration
- multiple devices per account
- synchronized Master Key backup
- vault sharing
- advanced offline-first features

## Document Governance

- this document must only be updated by explicit product decision
- any requirement conflicting with this text must be treated as blocked until formal review
- there are no parallel planning documents for V1

## Absolute Priority

Security of the architecture, implementation consistency, and predictable behavior on a single device.
