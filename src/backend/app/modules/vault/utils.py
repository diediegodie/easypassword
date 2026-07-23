from __future__ import annotations

import base64
import hashlib

MIN_BLOB_LENGTH = 1 + 12 + 16
MAX_BLOB_BYTES = 65_536
SUPPORTED_BLOB_VERSION = 1


def parse_blob_v1(blob: str) -> bytes:
    if not isinstance(blob, str):
        raise ValueError("malformed or non-base64 blob")

    try:
        decoded = base64.b64decode(blob, validate=True)
    except Exception as exc:
        raise ValueError("malformed or non-base64 blob") from exc

    if len(decoded) < MIN_BLOB_LENGTH:
        raise ValueError("blob version not supported")

    if decoded[0] != SUPPORTED_BLOB_VERSION:
        raise ValueError("blob version not supported")

    if len(decoded) > MAX_BLOB_BYTES:
        raise ValueError("decoded blob exceeds hard limit")

    return decoded


def format_blob_v1(blob_bytes: bytes) -> str:
    return base64.b64encode(blob_bytes).decode("ascii")


def hash_blob(blob_bytes: bytes) -> str:
    return hashlib.sha256(blob_bytes).hexdigest()
