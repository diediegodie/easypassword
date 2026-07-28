from prometheus_client import Counter, Gauge, Histogram

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

vault_auth_token_validation_latency_seconds = Histogram(
    "vault_auth_token_validation_latency_seconds",
    "Latency of token validation in seconds",
)

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

replay_cache_hits_total = Counter(
    "replay_cache_hits_total",
    "Count of replay cache hits (duplicate blobs detected)",
)

replay_cache_misses_total = Counter(
    "replay_cache_misses_total",
    "Count of replay cache misses (new blobs accepted)",
)

replay_cache_evictions_total = Counter(
    "replay_cache_evictions_total",
    "Count of replay cache evictions (entries expired)",
)

replay_cache_hit_rate = Histogram(
    "replay_cache_hit_rate",
    "Replay cache hit rate (percentage)",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

replay_cache_size = Gauge(
    "replay_cache_size",
    "Current number of entries in replay cache",
)

vault_iv_conflicts_total = Counter(
    "vault_iv_conflicts_total",
    "Count of duplicate IV conflicts detected within user context",
)
