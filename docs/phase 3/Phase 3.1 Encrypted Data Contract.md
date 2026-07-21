# Phase 3.1 Encrypted Data Contract

## Scope and Purpose

**Scope:** Define the normative, auditable contract and operational invariants required to implement Phase 3.1 - Encrypted Data Contract - so the system stores only encrypted blobs plus allowed plaintext metadata, the backend never receives decryption keys, and no backend flow performs decryption.

**Purpose:** Provide a concise, unambiguous source of truth for implementers, QA, SRE, and auditors. All implementation artifacts (full code, tests, CI scripts, monitoring rules, playbooks, and test vectors) are referenced from this document and stored as companion files in the repository.

## Acceptance Criteria (must be satisfied to close Phase 3.1)

- API contract is formal and versioned with exact blob format, examples, and error codes.
- Schemas validate base64 blobs, forbid extra fields, and return standardized errors.
- Backend stores blobs as LargeBinary and never decrypts; rejects extra fields and suspicious key-like fields.
- Frontend produces blobs in the specified format (AES‑GCM, IV unique per operation), never sends keys.
- Tests include unit, integration, adversarial (fuzzing) coverage and public test vectors.
- Size and rate limits are enforced client and server side.
- Logging policy prevents any logging of blobs or keys; automated log scans verify compliance.
- Migration and incident playbooks exist and are tested in staging.
- Audit evidence (test artifacts, vectors, CI outputs, monitoring dashboards) is collected and indexed.

## Canonical API Contract (normative)

### Blob format (canonical)

```
blob_v1 = base64( version(1 byte) || iv(12 bytes) || ciphertext || tag(16 bytes) )
```

**Allowed metadata:**  
`service_name`, `login_name` (max 255 characters each).

### Canonical API request/response (examples)

#### Create request

```json
{
  "service_name": "string (required, max 255)",
  "login_name": "string (required, max 255)",
  "password_blob": "string (required, base64 blob_v1)",
  "notes_blob": "string (optional, base64 blob_v1)"
}
```

#### Item response

```json
{
  "id": "uuid",
  "service_name": "string",
  "login_name": "string",
  "password_blob": "string (base64 blob_v1)",
  "notes_blob": "string | null",
  "created_at": "datetime",
  "updated_at": "datetime",
  "blob_version_detected": 1,
  "migration_recommended": false
}
```

#### Response header (recommended)

```
X-Vault-Blob-Version: 1
```

### Error catalog (canonical codes)

- `ERR_INVALID_BLOB` - malformed or non‑base64 blob (HTTP 422).
- `ERR_EXTRA_FIELDS` - payload contains fields not allowed (HTTP 422).
- `ERR_SUSPICIOUS_KEY` - payload contains key-like fields (HTTP 400).
- `ERR_BLOB_TOO_LARGE` - decoded blob exceeds hard limit (HTTP 413).
- `ERR_UNSUPPORTED_BLOB_VERSION` - blob version not supported (HTTP 422).
- `ERR_AAD_MISMATCH` - AAD authentication failed (HTTP 401).
- `ERR_REPLAY_DETECTED` - duplicate blob detected within replay window (HTTP 400).

## Canonical Crypto Rules and Client Key Lifecycle

### Blob format and IV/tag

- **Version byte:** 1 (0x01) prefix.
- **IV:** 12 bytes, unique per encryption operation.
- **Tag:** 16 bytes (AES‑GCM).
- **Encoding:** raw bytes concatenated as `[version][iv][ciphertext+tag]`, then base64 encoded.

### AAD canonicalization (required)

- **Field order:** `user_id`, `item_id`, `service_name` (exact order).
- **Normalization:** apply Unicode NFC to each field.
- **Separator:** ASCII Unit Separator `0x1F` between fields.
- **Encoding:** UTF‑8 bytes of the concatenation.
- **AAD example bytes:** `UTF8(user_id) + 0x1F + UTF8(item_id) + 0x1F + UTF8(service_name)`.

### KDF canonical parameters (authoritative)

- **Primary:** PBKDF2‑HMAC‑SHA256.
- **Salt length:** 16 bytes (random per user).
- **Iterations:** 310,000.
- **Output length:** 32 bytes (256 bits).
- **Derived key usage:** derive AES‑GCM 256‑bit master key.
- **Test vectors:** include at least one derived‑key vector (password + salt → derived key) in `/tests/vectors/`.

### IV Generation Strategy
- **IV Requirements:**
  - **Uniqueness:** IVs **must** be unique per encryption operation.
  - **Generation:** IVs **must** be generated using a cryptographically secure pseudorandom number generator (CSPRNG).
    - **Web clients:** `crypto.getRandomValues()` (Web Crypto API) is the normative method.
    - **Mobile clients:** `SecureRandom` (Android) / `SecRandomCopyBytes` (iOS).
  - **Concurrency:** In offline or concurrent environments (e.g., mobile + sync), clients **must** use a monotonic counter or device-specific nonce to avoid IV reuse. Fallback to CSPRNG if counters are exhausted.

### Key Rotation Triggers
- **Salt Rotation:**
  - Rotate the KDF salt **immediately** after a suspected compromise.
  - Rotate the KDF salt **proactively** every 2 years or after 100,000 derivations, whichever comes first.
- **Master Key Rotation:**
  - Derive a new master key **immediately** after a suspected compromise.
  - Derive a new master key **proactively** every 5 years or after regulatory changes.

### Replay Protection Policy

- **Nonce or timestamp in AAD:** Clients **must** include a monotonically increasing nonce or Unix timestamp in the AAD to prevent replay attacks. The nonce **must** be unique per item per operation.
- **Duplicate detection:** The backend **must** maintain a configurable replay cache (e.g., Redis) storing blob hashes observed within a configurable time window (default: 5 minutes).
  - **Cache key format:** `replay:{user_id}:{blob_hash}`.
  - **TTL:** entries **must** expire after the configured window (default 300 s).
  - **Hash:** SHA‑256 of the raw (pre‑base64) blob bytes.
  - **Rejection:** The backend **must** reject blobs whose hash matches a cached entry, returning `ERR_REPLAY_DETECTED` (HTTP 400).
- **Cache sizing:** The replay cache **must** be sized to accommodate peak write throughput; entries **must** expire after the configured window.

### Client responsibilities

- Encrypt all sensitive fields client‑side using AES‑GCM with AAD as specified.
- Never send decryption keys, raw key material, or key derivation secrets to the backend.
- Enforce size limits pre‑upload and return `ERR_BLOB_TOO_LARGE` to the user if exceeded.
- Store keys securely per platform (Keychain, Android Keystore, IndexedDB + WebCrypto best practices). See companion file `/docs/key_lifecycle.md`.

### Server responsibilities

- Treat blobs as opaque: decode base64 only to store as LargeBinary; never attempt decryption.
- Re‑encode stored bytes to base64 when returning to clients.
- Reject payloads with extra fields (`extra="forbid"`) or suspicious key names.
- Emit `blob_version_detected` and `migration_recommended` in responses.

## Operational Invariants, Limits, Tests, and Monitoring

### Operational invariants (non‑negotiable)

- Backend never receives decryption keys.
- Backend never performs decryption.
- Only allowed metadata (`service_name`, `login_name`) may be stored in plaintext.
- **Vault operations require an active backend connection; offline functional use is out of scope for Phase 3.1.**

### Log Retention and Protection Policy

- **Retention:** Application logs **must** be retained for a maximum of 90 days.
- **Encryption:** Logs **must** be encrypted at rest using AES-256 or equivalent.
- **Access:** Log access **must** be restricted to authorized personnel and audited quarterly.
- **Blob Scanning:** Automated log scans **must** run in CI to detect and redact base64-like strings (e.g., `[A-Za-z0-9+/]{40,}={0,2}`).

### Size and rate limits

- **Hard blob size limit:** 65,536 bytes (64 KB). Server returns `ERR_BLOB_TOO_LARGE` (HTTP 413).
- **Recommended client target:** ≤ 16 KB.
- **Alert threshold:** > 8 KB.
- **Rate limits (examples):** `POST /vault` 20/min, `PUT /vault/{id}` 20/min, `GET /vault` 60/min, `GET /vault/{id}` 120/min.

### Backup Restoration Checklist

- **Pre-Restore:**
  - Verify backup integrity using checksums or digital signatures.
  - Ensure backup encryption keys are available and accessible.
- **Post-Restore:**
  - Run a script to validate blob integrity (e.g., decode base64, verify version byte, check tag).
  - Reject and quarantine invalid blobs for manual review.
  - Log restoration events for audit purposes.

### Validation and tests (must exist)

- **Schema tests:** `extra="forbid"`, base64 validation, `parse_blob_v1` checks.
- **Backend tests:** store bytes unchanged, re‑encode symmetry, reject suspicious fields.
- **Frontend tests:** encrypt/decrypt symmetry, AAD verification, pre‑upload size checks.
- **Adversarial tests:** truncated blobs, invalid tag, wrong version, oversized blobs.
- **Fuzzing:** random base64 payloads and malformed JSON.
- **E2E tests:** FE encrypt → BE store → FE fetch → FE decrypt.
- **Automated log scan:** CI job that searches application logs for base64‑like strings and fails if found. Example heuristic: search for `[A-Za-z0-9+/]{40,}={0,2}` excluding known test vectors.
- **Backup verification:** CI script verifies backup encryption metadata and key separation (backup KMS key ≠ DB KMS key).

### Performance Testing Requirements

- **Load tests:** Mandatory load tests **must** exercise blob operations at sizes of 1 KB, 16 KB, and 64 KB under concurrent load simulating peak throughput.
- **Stress tests:** Stress tests **must** push the system beyond rate limits to verify graceful degradation and error handling.
- **Latency benchmarks:** Benchmarks **must** measure and report:
  - Client-side encryption and decryption latency per blob size.
  - API round-trip latency (POST /vault, PUT /vault/{id}, GET /vault/{id}) under rate-limit pressure.
- **Thresholds:** Latency **must** remain within SLA-defined limits (e.g., p99 < 500 ms for writes, p99 < 200 ms for reads) under normal load.
- **CI integration:** Performance tests **must** run in CI on every pull request targeting main; regressions exceeding 20 % **must** block merge.

### Monitoring and alerts (examples)

- **Alert: suspicious key fields spike - PromQL:**

  ```promql
  sum(rate(vault_errors_total{code="ERR_SUSPICIOUS_KEY"}[5m])) > 1
  ```

- **Alert: malformed blob rate - PromQL:**

  ```promql
  sum(rate(vault_errors_total{code="ERR_INVALID_BLOB"}[5m])) > 5
  ```

- **Alert: oversized blob attempts - PromQL:**

  ```promql
  sum(rate(vault_errors_total{code="ERR_BLOB_TOO_LARGE"}[5m])) > 0
  ```

- **Alert: write latency SLA breach (p99 > 500 ms) - PromQL:**

  ```promql
  histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{job="app", route="vault_write"}[5m])) > 0.5
  ```

- **Alert: read latency SLA breach (p99 > 200 ms) - PromQL:**

  ```promql
  histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{job="app", route="vault_read"}[5m])) > 0.2
  ```

- **Alert: replay detection spike - PromQL:**

  ```promql
  sum(rate(vault_errors_total{code="ERR_REPLAY_DETECTED"}[5m])) > 0
  ```

- **Log query example (Loki):**

  ```promql
  {job="app"} |= "ERR_INVALID_BLOB" | count_over_time({job="app"}[5m]) > 5
  ```

## Migration, Incident Playbook, Audit Evidence, and Final Checklist

### Migration signals and flow

- **Response fields:** `blob_version_detected` (int), `migration_recommended` (bool).
- **Migration helper API (spec):**
  - `POST /vault/{id}/mark-stale` - mark item `needs_migration=true`. Audit event `vault.item.mark_stale`.
  - `PUT /vault/{id}` - client re‑encrypts and sets `needs_migration=false`. Audit event `vault.item.migrated`.
- **Migration flow:** client detects `migration_recommended` → decrypts old blob locally → encrypts with new version → PUT updated blob.

### Deprecation Policy

- **Support window:** Older blob versions **must** remain fully supported for a minimum of 18 months after the release of a new version.
- **Mandatory migration:** After the 18‑month window, migration becomes mandatory. The backend **must** reject blobs using deprecated versions, returning `ERR_UNSUPPORTED_BLOB_VERSION` (HTTP 422).
- **Advance notice:** At least 90 days before the deprecation deadline, the backend **must** emit `migration_recommended: true` on all affected items and clients **must** surface a migration prompt to users.
- **Exception handling:** Clients that fail to migrate within the window **must** be blocked from writing until they upgrade; reads of deprecated blobs **may** remain permitted for a grace period of up to 30 days after the deadline.

### Key compromise playbook (summary)

1. **Detect** - *Incident Commander* authorizes alert response; *Security Engineer* analyzes alerts and identifies scope.
2. **Contain** - *Security Engineer* marks affected items `needs_migration` and tightens rate limits; *QA Auditor* validates containment measures.
3. **Recover** - *Security Engineer* executes key rotation and prescribes controlled re‑encryption workflow; *QA Auditor* runs post‑remediation test suite and signs off.
4. **Re‑encrypt** - clients re‑encrypt items client‑side and clear `needs_migration`; *QA Auditor* verifies completion.
5. **Post‑incident** - *Security Engineer* rotates keys and audits logs; *Communications Lead* drafts and publishes user notifications; *Incident Commander* approves return to service and authorizes public statements.

### Incident Governance Roles

- **Incident Commander:** Owns the incident response process; coordinates all roles, declares severity, and authorizes communications.
- **Security Engineer:** Investigates root cause, identifies affected items, prescribes remediation steps, and validates key rotation.
- **QA Auditor:** Verifies that remediation actions (re‑encryption, migration) complete successfully; signs off on test evidence and audit artifacts.
- **Communications Lead:** Drafts and approves user-facing notifications; manages disclosure timeline in coordination with the Incident Commander.

| Role | Detection | Containment | Recovery | User Notification |
|------|-----------|-------------|----------|--------------------|
| Incident Commander | Authorizes alert response | Declares incident open | Approves return to service | Authorizes public statements |
| Security Engineer | Analyzes alerts, identifies scope | Implements replay cache, rate-limit tightening | Executes key rotation, re‑encryption workflow | Provides technical facts to Communications Lead |
| QA Auditor | - | Validates containment measures | Runs post‑remediation test suite, signs off | - |
| Communications Lead | - | - | - | Drafts and publishes user notifications |

### Audit evidence index (must be produced)

- `docs/api-contracts-v1.json` - canonical contract.
- `docs/phase3_acceptance_checklist.md` - one‑page checklist.
- `tests/vectors/` - canonical test vectors (JS/Python/Kotlin/Swift).
- `utils/encoding.py` - canonical parse/build functions.
- `ops/ci/log_scan.sh` and `ops/ci/backup_verify.sh` - CI verification helpers.
- `ops/monitoring/alerts.prom` and `ops/monitoring/alerts.loki` - alert rules.
- `ops/playbooks/key_compromise.md` - full incident playbook.
- `audit/` - test run artifacts, verification logs, and mapping file → change → reason.

### Cross-Platform Test Vector Guarantee
- **Test Vectors:**
  - **Scope:** Include at least one public, interoperable test vector for each supported platform (JS, Python, Kotlin, Swift).
  - **Validation:** Vectors **must** validate:
    - Blob encoding/decoding symmetry.
    - AAD canonicalization.
    - KDF derivation.
    - AES-GCM encryption/decryption.
  - **Storage:** Vectors **must** be stored in `/tests/vectors/` with platform-specific subdirectories.
  - **CI:** Vectors **must** be exercised in CI on every pull request to ensure cross-platform consistency; a CI failure **must** block merge.

🔗 Final Acceptance Checklist → Phase 3.1 Contract Mapping

| Checklist Item | Corresponding Section in Phase 3.1 Contract |
|---|---|
| `api-contracts-v1.json` contains blob_v1, AAD canonicalization, KDF params, error catalog, and versioning policy | Canonical API Contract → Blob format, AAD canonicalization, KDF parameters, Error catalog, Versioning Policy |
| Schemas use `extra="forbid"` and validators for base64 and blob format | Canonical API Contract → Schemas validate base64 blobs, forbid extra fields |
| Backend stores LargeBinary and never decrypts; no `.encode("utf-8")`/`.decode("utf-8")` remains in vault paths | Operational Invariants → Backend never decrypts; Server Responsibilities → Treat blobs as opaque |
| Middleware rejects suspicious key fields and unexpected large base64 fields | Server Responsibilities → Reject payloads with extra fields or suspicious key names |
| Frontend encryption implements AES‑GCM blob_v1 with AAD canonicalization and KDF parameters | Client Responsibilities → Encrypt client-side using AES‑GCM with AAD and KDF parameters |
| Client enforces pre‑upload size checks and returns `ERR_BLOB_TOO_LARGE` | Client Responsibilities → Enforce size limits pre-upload; Operational Invariants → Size and rate limits |
| Unit, integration, adversarial, fuzz, and E2E tests pass | Validation and Tests → Unit, Integration, Adversarial, Fuzzing, E2E tests |
| Automated log scan and backup verification CI checks pass | Log Retention and Protection Policy → Automated log scans; Backup Restoration Checklist → Verification scripts |
| Monitoring alerts are implemented and tested | Monitoring and Alerts → PromQL and Loki rules |
| Migration helper API and incident playbook are documented and exercised in staging | Migration, Incident Playbook → Migration flow & Key compromise playbook |
| Audit package with test artifacts and mapping document is assembled | Audit Evidence Index → `docs/`, `tests/`, `utils/`, `ops/`, `audit/` |
| Deprecation enforcement verified (`ERR_UNSUPPORTED_BLOB_VERSION` returned after deadline; `ERR_REPLAY_DETECTED` returned for duplicate blobs) | Deprecation Policy → Mandatory migration; Replay Protection Policy → Rejection |
| Replay cache tested: duplicate blob submissions return `ERR_REPLAY_DETECTED` (HTTP 400) | Replay Protection Policy → Duplicate detection and rejection |
| Cross‑platform test vectors (JS, Python, Kotlin, Swift) validated in CI | Cross‑Platform Test Vector Guarantee → CI integration |

## Where to find companion artifacts (recommended repo layout)

- `docs/api-contracts-v1.json` - canonical contract (machine‑readable).
- `docs/phase3_acceptance_checklist.md` - one‑page checklist.
- `docs/key_lifecycle.md` - key derivation and storage guidance.
- `tests/vectors/` - test vectors and verification scripts.
- `utils/encoding.py` - parse/build functions for blob_v1.
- `ops/ci/log_scan.sh` and `ops/ci/backup_verify.sh` - CI helpers.
- `ops/monitoring/` - Prometheus and Loki rules.
- `ops/playbooks/key_compromise.md` - incident playbook.
- `audit/` - test run artifacts and mapping file → change → reason.