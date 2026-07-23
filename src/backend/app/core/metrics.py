from prometheus_client import Counter, Histogram

# Token validation metrics
vault_auth_token_validations_total = Counter(
    "vault_auth_token_validations_total",
    "Count of token validation attempts",
    ["status"],
)

vault_auth_token_expiry_failures_total = Counter(
    "vault_auth_token_expiry_failures_total",
    "Count of requests rejected due to expired tokens",
)

vault_auth_token_scope_failures_total = Counter(
    "vault_auth_token_scope_failures_total",
    "Count of requests rejected due to insufficient scope",
)

# Optional: latency for token validation
vault_auth_token_validation_latency_seconds = Histogram(
    "vault_auth_token_validation_latency_seconds",
    "Latency of token validation in seconds",
)

# Revocation check metrics
vault_auth_revocation_checks_total = Counter(
    "vault_auth_revocation_checks_total",
    "Count of revocation checks performed",
)

vault_auth_revocation_misses_total = Counter(
    "vault_auth_revocation_misses_total",
    "Count of revocation checks that found token not revoked",
)

vault_auth_revocation_hits_total = Counter(
    "vault_auth_revocation_hits_total",
    "Count of revocation checks that found token revoked",
)
