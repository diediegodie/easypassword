"""Centralized Redis key patterns for EasyPassword.

This module only centralizes the key patterns discovered in the repo
and does NOT change any literal production key values.
"""

from __future__ import annotations

# Patterns discovered in the repository
WEBAUTHN_CHALLENGE_KEY = "webauthn:challenge:{}"
DEVICE_REAUTH_REQUIRED_KEY = "device:reauth:{}"
RATE_LIMIT_KEY = "rate_limit:{client_ip}:{user}:{path}"

__all__ = [
    "WEBAUTHN_CHALLENGE_KEY",
    "DEVICE_REAUTH_REQUIRED_KEY",
    "RATE_LIMIT_KEY",
]
