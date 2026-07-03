# EasyPassword — Definitive Roadmap V1 (Execution Checklist)

Official base: product_source_of_truth.md
Objective: execute the V1 of the product from start to finish without scope deviation.

## Execution Rules (Mandatory)

- Fully respect the V1 scope defined in the official document.
- Do not implement account recovery, device migration, or multi-device in V1.
- Do not enable offline functional use in V1.
- Keep Angular as the only frontend stack.
- Maintain PostgreSQL as the session source of truth.
- Use Redis only for ephemeral data (challenge, rate limit, and short expiration).

## Phase 0 — Project Preparation

### 0.1 Repository and organization
- [x] Confirm folder structure for frontend, backend, infrastructure, and docs.
- [x] Define branch convention and commit standard.
- [x] Define CODEOWNERS or module owners.

### 0.2 Local environment
- [x] Create Docker Compose environment with services: frontend, backend, postgres, and redis.
- [x] Ensure all services start with a single command.
- [x] Create an example environment variables file.

### 0.3 Minimum quality
- [x] Configure lint and formatting for frontend and backend.
- [x] Configure automated tests with CI execution.
- [x] Define merge rule: no green tests, no merge.

## Phase 1 — Backend Base (FastAPI + Database + Session)

### 1.1 API Foundation
- [x] Initialize FastAPI project with modular structure (auth, vault, session, infra).
- [x] Define environment-based configuration layer.
- [x] Configure centralized error and log handling.

### 1.2 Modeling and migrations
- [x] Implement tables users, devices, vaults, and sessions.
- [x] Create Alembic migrations for all tables.
- [x] Apply integrity constraints (FK, unique, essential indexes).
- [x] Create index for queries by user_id and device_id on critical tables.

### 1.3 Session and tokens (closed parameters)
- [x] Implement JWT access token with 5-minute validity.
- [x] Implement opaque refresh token with 7-day validity.
- [x] Store refresh token only as a hash in PostgreSQL.
- [x] Implement mandatory refresh token rotation on each renewal.
- [x] Implement immediate session revocation in case of reuse detection.
- [x] Configure HttpOnly and Secure cookies for token transport.
- [x] Ensure Redis is not the session authority.

### 1.4 Ephemeral components
- [x] Implement WebAuthn challenge storage in Redis.
- [x] Configure challenge TTL to 90 seconds.
- [x] Implement basic rate limiting by IP/user on sensitive endpoints (keyed by client_ip + user + path).

## Phase 2 — WebAuthn Authentication (Single Device)

### 2.1 Credential registration
- [x] Create WebAuthn registration initiation endpoint.
- [x] Create WebAuthn registration completion endpoint.
- [x] Persist credential_id, public_key, and device metadata.
- [x] Link account to a single active device.

### 2.2 Recurring login
- [x] Create WebAuthn authentication initiation endpoint.
- [x] Create WebAuthn authentication completion endpoint.
- [x] Validate challenge, signature, and device state.
- [x] Issue session only after valid authentication.

### 2.3 Access security rules
- [ ] Require WebAuthn reauthentication after 60 seconds of inactivity.
- [ ] Apply 120-second clock skew tolerance.
- [ ] Block authentication from inactive devices.
- [ ] Ensure device switching is out of V1 scope.

## Phase 3 — Client-Side Encryption + API Contracts

### 3.1 Encrypted data contract
- [ ] Define vault payload containing only encrypted blobs and allowed metadata.
- [ ] Ensure backend never receives decryption key.
- [ ] Ensure backend does not perform decryption in any flow.

### 3.2 Mandatory cryptographic rules
- [ ] Implement AES-GCM on the client for sensitive data.
- [ ] Generate unique IV per operation with crypto.getRandomValues().
- [ ] Prevent IV reuse with the same key.
- [ ] Validate Master Key creation and usage flow only on the device.

### 3.3 Cryptographic error handling
- [ ] Display clear error when local key is unavailable.
- [ ] Securely invalidate session in case of critical integrity failure.

## Phase 4 — Frontend Angular (UI + State + Integration)

### 4.1 Frontend foundation
- [ ] Initialize Angular app with feature-based architecture.
- [ ] Configure HttpClient as the single communication layer.
- [ ] Configure Signals for global/local state.
- [ ] Do not include Axios or other HTTP stacks.

### 4.2 Authentication flows
- [ ] Implement WebAuthn access screen and registration flow.
- [ ] Implement recurring login flow with passkeys.
- [ ] Implement session expiration and transparent renewal.
- [ ] Implement inactivity lock after 60 seconds.

### 4.3 Vault flows
- [ ] Implement vault item listing.
- [ ] Implement creation, editing, and deletion of entries.
- [ ] Implement quick password copy.
- [ ] Implement local decryption only at the time of use.

### 4.4 Connectivity rules
- [ ] Block functional use when offline.
- [ ] Display connectivity status and clear message to the user.
- [ ] Prevent vault read/write without active connection.

## Phase 5 — PWA and iPhone X Support

### 5.1 PWA
- [ ] Configure manifest and icons.
- [ ] Configure standalone mode.
- [ ] Configure service worker for static assets only.
- [ ] Ensure service worker does not enable offline functional use.

### 5.2 V1 support matrix
- [ ] Validate main behavior on iPhone X.
- [ ] Validate on iOS 16.7.x.
- [ ] Validate on Safari iOS and standalone PWA mode.
- [ ] Record that other devices are outside V1 support commitment.

## Phase 6 — Security Hardening

### 6.1 API and session
- [ ] Apply CSP as needed for hosted frontend.
- [ ] Apply CSRF for flows with session cookies when applicable.
- [ ] Apply restrictive CORS policy.
- [ ] Enforce HTTPS in all external environments.

### 6.2 Observability and auditing
- [ ] Log critical authentication and session revocation events.
- [ ] Log WebAuthn failures and refresh token reuse attempts.
- [ ] Define minimum error and availability dashboard.

### 6.3 Security tests
- [ ] Test challenge, access token, and refresh token expiration.
- [ ] Test revocation by reuse detection.
- [ ] Test offline access attempts and validate blocking.
- [ ] Test single-device with second device attempt.

## Phase 7 — CI/CD and Deployment (Render)

### 7.1 CI Pipeline
- [ ] Run lint, tests, and build on pull request.
- [ ] Block merge with failed pipeline.
- [ ] Publish build artifacts when applicable.

### 7.2 Production preparation
- [ ] Configure services on Render for frontend and backend.
- [ ] Configure managed PostgreSQL and backup strategy.
- [ ] Configure Redis for ephemeral challenge/rate limit use.
- [ ] Configure environment variables and secrets with rotation.

### 7.3 Go-live
- [ ] Run migrations in production.
- [ ] Validate complete flow: registration, login, session, vault, logout.
- [ ] Validate security headers and HTTPS.
- [ ] Publish V1 version and monitor the first 24 hours.

## Phase 8 — V1 Acceptance Criteria

- [ ] User can register device via WebAuthn on first access.
- [ ] User can access daily with passkey/biometrics/system PIN.
- [ ] Session respects all defined times (challenge, access, refresh, inactivity).
- [ ] Vault works with local encryption and backend without decryption.
- [ ] Application does not allow offline functional use.
- [ ] Application meets main support defined for iPhone X.
- [ ] CI/CD pipeline and Render deployment are stable.

## Phase 9 — V1 Closure

- [ ] Consolidate checklist with evidence of completion per item.
- [ ] Freeze V1 backlog and open V2 backlog separately.
- [ ] Formalize V1 release notes.
- [ ] Explicitly classify pending items as V2.

## Change Control

- [ ] Any changes to this roadmap must reference the official product document.
- [ ] Any item that contradicts the source of truth must be blocked until product approval.
