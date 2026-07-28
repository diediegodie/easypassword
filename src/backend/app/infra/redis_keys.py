from __future__ import annotations

WEBAUTHN_CHALLENGE_KEY = "webauthn:challenge:{}"
DEVICE_REAUTH_REQUIRED_KEY = "device:reauth:{}"
RATE_LIMIT_KEY = "rate_limit:{client_ip}:{user}:{path}"
REPLAY_CACHE_KEY = "replay:{user_id}:{blob_hash}"
IV_CACHE_KEY = "iv:{user_id}:{iv_hex}"

__all__ = [
    "WEBAUTHN_CHALLENGE_KEY",
    "DEVICE_REAUTH_REQUIRED_KEY",
    "RATE_LIMIT_KEY",
    "REPLAY_CACHE_KEY",
    "IV_CACHE_KEY",
]
