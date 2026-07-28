from __future__ import annotations

import base64
import hashlib
import os
import struct
import time
import unicodedata

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VERSION_BYTE = b"\x01"
IV_LENGTH = 12
TAG_LENGTH = 16
SALT_LENGTH = 16
PBKDF2_ITERATIONS = 310_000
PBKDF2_HASH = hashes.SHA256()
DERIVED_KEY_LENGTH = 32
AAD_SEPARATOR = b"\x1f"
IV_DEVICE_PREFIX_LENGTH = 4
IV_COUNTER_LENGTH = 4
IV_RANDOM_LENGTH = 4
IV_COUNTER_MAX = 0xFFFFFFFF


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from a password and salt using PBKDF2-HMAC-SHA256."""
    if len(salt) != SALT_LENGTH:
        raise ValueError(f"Salt must be {SALT_LENGTH} bytes")

    kdf = PBKDF2HMAC(
        algorithm=PBKDF2_HASH,
        length=DERIVED_KEY_LENGTH,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _normalize_aad_field(field: str) -> bytes:
    """Normalize a string field for AAD using Unicode NFC and encode to UTF-8 bytes."""
    return unicodedata.normalize("NFC", field).encode("utf-8")


def _device_prefix(device_id: str) -> bytes:
    """Derive a 4-byte device-specific prefix from a device identifier."""
    digest = hashlib.sha256(device_id.encode("utf-8")).digest()
    return digest[:IV_DEVICE_PREFIX_LENGTH]


def generate_iv(
    device_id: str | None = None,
    counter: int | None = None,
) -> bytes:
    """Generate a 12-byte IV with optional device-specific construction."""
    if device_id is None:
        return os.urandom(IV_LENGTH)

    prefix = _device_prefix(device_id)

    if counter is not None:
        if not (0 <= counter <= IV_COUNTER_MAX):
            raise ValueError(
                f"counter must be in range [0, {IV_COUNTER_MAX}], got {counter}"
            )
        middle = struct.pack(">I", counter)
        import hashlib

        combined = device_id.encode("utf-8") + str(counter).encode("utf-8")
        deterministic_tail = hashlib.sha256(combined).digest()[:4]
        iv = prefix + middle + deterministic_tail
    else:
        middle = struct.pack(">I", int(time.time()) & IV_COUNTER_MAX)
        random_tail = os.urandom(IV_RANDOM_LENGTH)
        iv = prefix + middle + random_tail

    assert len(iv) == IV_LENGTH
    return iv


def extract_iv(blob: str) -> bytes:
    """Extract the IV from a base64-encoded blob."""
    try:
        data = base64.b64decode(blob, validate=True)
    except Exception as exc:
        raise ValueError("Invalid base64 encoding") from exc
    if len(data) < 1 + IV_LENGTH:
        raise ValueError("Blob too short for IV")
    version = data[0:1]
    if version != b"\x01":
        raise ValueError(f"Unsupported blob version: {version.decode('latin-1')}")
    return data[1 : 1 + IV_LENGTH]


def get_iv_origin_metadata(iv: bytes) -> dict[str, bytes | int | str | None]:
    """Decompose a 12-byte IV into its origin metadata components."""
    if len(iv) != IV_LENGTH:
        raise ValueError(f"IV must be {IV_LENGTH} bytes, got {len(iv)}")
    device_prefix = iv[:IV_DEVICE_PREFIX_LENGTH]
    middle = struct.unpack(
        ">I", iv[IV_DEVICE_PREFIX_LENGTH : IV_DEVICE_PREFIX_LENGTH + IV_COUNTER_LENGTH]
    )[0]
    tail = iv[IV_DEVICE_PREFIX_LENGTH + IV_COUNTER_LENGTH :]
    _REASONABLE_TIMESTAMP_MIN = 1_000_000_000
    _REASONABLE_TIMESTAMP_MAX = 2_000_000_000
    if _REASONABLE_TIMESTAMP_MIN <= middle <= _REASONABLE_TIMESTAMP_MAX:
        origin = "random"
        timestamp = middle
        counter = None
    else:
        origin = "device_counter"
        timestamp = None
        counter = middle
    return {
        "origin": origin,
        "device_id": None,
        "device_prefix": device_prefix,
        "counter": counter,
        "timestamp": timestamp,
        "random": tail,
        "raw": iv,
    }


def build_aad(user_id: str, item_id: str, service_name: str) -> bytes:
    """Construct the Additional Authenticated Data (AAD) as per spec."""
    parts = [
        _normalize_aad_field(user_id),
        _normalize_aad_field(item_id),
        _normalize_aad_field(service_name),
    ]
    return AAD_SEPARATOR.join(parts)


def encrypt(
    plaintext: bytes,
    key: bytes,
    user_id: str,
    item_id: str,
    service_name: str,
    device_id: str | None = None,
    counter: int | None = None,
) -> str:
    """Encrypt plaintext using AES-GCM with the derived key and AAD."""
    if len(key) != DERIVED_KEY_LENGTH:
        raise ValueError(f"Key must be {DERIVED_KEY_LENGTH} bytes")

    iv = generate_iv(device_id=device_id, counter=counter)
    if len(iv) != IV_LENGTH:
        raise RuntimeError("Failed to generate sufficient random IV")

    aad = build_aad(user_id, item_id, service_name)

    aesgcm = AESGCM(key)
    ciphertext_tag = aesgcm.encrypt(iv, plaintext, aad)

    blob = VERSION_BYTE + iv + ciphertext_tag

    return base64.b64encode(blob).decode("ascii")


def decrypt(
    blob: str,
    key: bytes,
    user_id: str,
    item_id: str,
    service_name: str,
) -> bytes:
    """Decrypt a blob using AES-GCM with the derived key and AAD."""
    if len(key) != DERIVED_KEY_LENGTH:
        raise ValueError(f"Key must be {DERIVED_KEY_LENGTH} bytes")
    try:
        data = base64.b64decode(blob)

    except Exception as exc:
        raise ValueError("Invalid base64 encoding") from exc

    if not data.startswith(VERSION_BYTE):
        raise ValueError("Unsupported blob version")
    data = data[1:]

    if len(data) < IV_LENGTH:
        raise ValueError("Blob too short for IV")
    iv = data[:IV_LENGTH]

    ciphertext_tag = data[IV_LENGTH:]

    if len(ciphertext_tag) < TAG_LENGTH:
        raise ValueError("Ciphertext too short for tag")

    aad = build_aad(user_id, item_id, service_name)

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(iv, ciphertext_tag, aad)
    except InvalidTag:
        raise

    return plaintext


def generate_salt() -> bytes:
    """Generate a cryptographically secure random salt.
    Returns a 16-byte salt.
    """
    return os.urandom(SALT_LENGTH)


def derive_key_from_password(password: str) -> tuple[bytes, bytes]:
    """Generate a salt and derive a key from a password.
    Returns a tuple (salt, derived_key).
    """
    salt = generate_salt()
    key = derive_key(password, salt)
    return salt, key
