"""Unit tests for the vault crypto module.

Tests cryptographic primitives against canonical test vectors from:
tests/vectors/crypto_vectors_v1.json
"""

import json
import os
from pathlib import Path

import pytest

from app.modules.vault.crypto import (
    AAD_SEPARATOR,
    DERIVED_KEY_LENGTH,
    IV_LENGTH,
    PBKDF2_ITERATIONS,
    SALT_LENGTH,
    TAG_LENGTH,
    VERSION_BYTE,
    build_aad,
    decrypt,
    derive_key,
    encrypt,
    extract_iv,
    generate_iv,
    generate_salt,
    get_iv_origin_metadata,
)

VECTORS_PATH = (
    Path(__file__).parent.parent.parent / "tests" / "vectors" / "crypto_vectors_v1.json"
)
with open(VECTORS_PATH) as f:
    TEST_VECTORS = json.load(f)


pytestmark = pytest.mark.unit


class TestConstants:
    """Test that constants match the specification."""

    def test_version_byte(self):
        assert VERSION_BYTE == b"\x01"

    def test_iv_length(self):
        assert IV_LENGTH == 12

    def test_tag_length(self):
        assert TAG_LENGTH == 16

    def test_salt_length(self):
        assert SALT_LENGTH == 16

    def test_derived_key_length(self):
        assert DERIVED_KEY_LENGTH == 32

    def test_pbkdf2_iterations(self):
        assert PBKDF2_ITERATIONS == 310_000

    def test_aad_separator(self):
        assert AAD_SEPARATOR == b"\x1f"


class TestKDF:
    """Test PBKDF2 key derivation against test vectors."""

    def test_derive_key_vector(self):
        """Test KDF against canonical test vector kdf-001."""
        vectors = TEST_VECTORS["kdf"]["vectors"]
        for vec in vectors:
            password = vec["password"]
            salt = bytes.fromhex(vec["salt_hex"])
            expected_key = bytes.fromhex(vec["derived_key_hex"])

            derived = derive_key(password, salt)

            assert derived == expected_key, f"Failed for vector {vec['id']}"
            assert len(derived) == DERIVED_KEY_LENGTH

    def test_derive_key_invalid_salt_length(self):
        """Test that wrong salt length raises ValueError."""
        with pytest.raises(ValueError, match="Salt must be"):
            derive_key("password", b"short")


class TestAAD:
    """Test AAD canonicalization against test vectors."""

    def test_build_aad_vector(self):
        """Test AAD building against canonical test vectors."""
        vectors = TEST_VECTORS["aad"]["vectors"]
        for vec in vectors:
            aad = build_aad(
                user_id=vec["user_id"],
                item_id=vec["item_id"],
                service_name=vec["service_name"],
            )
            expected_hex = vec["aad_hex"]

            assert aad.hex() == expected_hex, f"Failed for vector {vec['id']}"

    def test_aad_field_order(self):
        """Test that AAD fields are in correct order: user_id, item_id, service_name."""
        aad = build_aad("user", "item", "service")
        parts = aad.split(AAD_SEPARATOR)
        assert parts[0] == b"user"
        assert parts[1] == b"item"
        assert parts[2] == b"service"

    def test_aad_nfc_normalization(self):
        """Test that NFC normalization is applied to all fields."""
        cafe_nfc = "café"
        cafe_nfd = "cafe\u0301"

        aad_nfc = build_aad("user", "item", cafe_nfc)
        aad_nfd = build_aad("user", "item", cafe_nfd)

        assert aad_nfc == aad_nfd

    def test_aad_utf8_encoding(self):
        """Test that AAD fields are UTF-8 encoded."""
        aad = build_aad("user", "item", "café")
        assert b"caf\xc3\xa9" in aad


class TestAES_GCM:
    """Test AES-GCM encryption/decryption against test vectors."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encrypt then decrypt returns original plaintext."""
        key = bytes.fromhex(
            "d51374d1cbb810c65c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )
        plaintext = b"test message"
        user_id = "usr_01"
        item_id = "itm_01"
        service_name = "GitHub"

        blob = encrypt(plaintext, key, user_id, item_id, service_name)
        decrypted = decrypt(blob, key, user_id, item_id, service_name)

        assert decrypted == plaintext

    def test_encrypt_decrypt_empty_plaintext(self):
        """Test encryption/decryption of empty plaintext."""
        key = bytes.fromhex(
            "d51374d1cbb810c65c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )
        plaintext = b""
        user_id = "usr_01"
        item_id = "itm_01"
        service_name = "GitHub"

        blob = encrypt(plaintext, key, user_id, item_id, service_name)
        decrypted = decrypt(blob, key, user_id, item_id, service_name)

        assert decrypted == plaintext

    def test_encrypt_produces_base64(self):
        """Test that encrypt produces valid base64 output."""
        key = bytes.fromhex(
            "d51374d1cbb810c66c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )
        blob = encrypt(b"test", key, "usr", "itm", "svc")

        import base64

        decoded = base64.b64decode(blob)
        assert len(decoded) > 1 + IV_LENGTH + TAG_LENGTH

    def test_encrypt_blob_format(self):
        """Test that blob format is [version][IV][ciphertext+tag]."""
        key = bytes.fromhex(
            "d51374d1cbb810c65c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )
        blob = encrypt(b"test", key, "usr", "itm", "svc")

        import base64

        data = base64.b64decode(blob)

        assert data[0:1] == VERSION_BYTE
        assert len(data) == 1 + IV_LENGTH + len(b"test") + TAG_LENGTH

    def test_decrypt_wrong_key_fails(self):
        """Test that decryption with wrong key fails."""
        key1 = bytes.fromhex(
            "d51374d1cbb810c65c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )
        key2 = bytes.fromhex(
            "0000000000000000000000000000000000000000000000000000000000000000"
        )

        blob = encrypt(b"test", key1, "usr", "itm", "svc")

        from cryptography.exceptions import InvalidTag

        with pytest.raises(InvalidTag):
            decrypt(blob, key2, "usr", "itm", "svc")

    def test_decrypt_wrong_aad_fails(self):
        """Test that decryption with wrong AAD fails."""
        key = bytes.fromhex(
            "d51374d1cbb810c65c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )

        blob = encrypt(b"test", key, "usr", "itm", "svc")

        from cryptography.exceptions import InvalidTag

        with pytest.raises(InvalidTag):
            decrypt(blob, key, "wrong", "itm", "svc")

    def test_decrypt_invalid_base64(self):
        """Test that invalid base64 raises ValueError."""
        key = bytes.fromhex(
            "d51374d1cbb810c65c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )

        with pytest.raises(ValueError, match="Invalid base64"):
            decrypt("not-valid-base64!!!", key, "usr", "itm", "svc")

    def test_decrypt_wrong_version(self):
        """Test that wrong version byte raises ValueError."""
        import base64

        key = bytes.fromhex(
            "d51374d1cbb810c65c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )

        blob_data = b"\x02" + b"\x00" * (1 + IV_LENGTH + 16)
        blob = base64.b64encode(blob_data).decode()

        with pytest.raises(ValueError, match="Unsupported blob version"):
            decrypt(blob, key, "usr", "itm", "svc")

    def test_decrypt_truncated_blob(self):
        """Test that truncated blob raises ValueError."""
        import base64

        key = bytes.fromhex(
            "d51374d1cbb810c65c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )

        blob_data = b"\x01" + b"\x00" * 5
        blob = base64.b64encode(blob_data).decode()

        with pytest.raises(ValueError, match="Blob too short"):
            decrypt(blob, key, "usr", "itm", "svc")

    def test_encrypt_invalid_key_length(self):
        """Test that wrong key length raises ValueError."""
        with pytest.raises(ValueError, match="Key must be"):
            encrypt(b"test", b"short", "usr", "itm", "svc")

    def test_decrypt_invalid_key_length(self):
        """Test that wrong key length raises ValueError on decrypt."""
        with pytest.raises(ValueError, match="Key must be"):
            decrypt("AQID", b"short", "usr", "itm", "svc")


class TestGenerateSalt:
    """Test salt generation."""

    def test_generate_salt_length(self):
        """Test that generated salt has correct length."""
        salt = generate_salt()
        assert len(salt) == SALT_LENGTH

    def test_generate_salt_random(self):
        """Test that generated salts are random."""
        salt1 = generate_salt()
        salt2 = generate_salt()
        assert salt1 != salt2


class TestCanonicalVectors:
    """Test against canonical test vectors from crypto_vectors_v1.json."""

    def test_kdf_canonical_vectors(self):
        """Verify all KDF test vectors pass."""
        vectors = TEST_VECTORS["kdf"]["vectors"]
        for vec in vectors:
            password = vec["password"]
            salt = bytes.fromhex(vec["salt_hex"])
            expected_key = bytes.fromhex(vec["derived_key_hex"])

            derived = derive_key(password, salt)
            assert derived == expected_key, f"KDF vector {vec['id']} failed"

    def test_aad_canonical_vectors(self):
        """Verify all AAD test vectors pass."""
        vectors = TEST_VECTORS["aad"]["vectors"]
        for vec in vectors:
            aad = build_aad(
                user_id=vec["user_id"],
                item_id=vec["item_id"],
                service_name=vec["service_name"],
            )
            expected_hex = vec["aad_hex"]
            assert aad.hex() == expected_hex, f"AAD vector {vec['id']} failed"

    def test_aes_gcm_canonical_vectors(self):
        """Verify all AES-GCM test vectors pass."""
        import hashlib

        vectors = TEST_VECTORS["aes_gcm"]["vectors"]
        for vec in vectors:
            key = bytes.fromhex(vec["key_hex"])
            plaintext = bytes.fromhex(vec["plaintext_hex"])
            iv = bytes.fromhex(vec["iv_hex"])
            expected_blob_hex = vec["blob_raw_hex"]
            expected_blob_base64 = vec["blob_base64"]

            aad = bytes.fromhex(vec["aad_hex"])

            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(key)
            ciphertext_tag = aesgcm.encrypt(iv, plaintext, aad)

            expected_blob = VERSION_BYTE + iv + ciphertext_tag

            assert (
                expected_blob.hex() == expected_blob_hex
            ), f"AES-GCM blob format {vec['id']} failed"

            import base64

            assert (
                base64.b64encode(expected_blob).decode() == expected_blob_base64
            ), f"AES-GCM base64 {vec['id']} failed"

            blob_sha256 = hashlib.sha256(expected_blob).hexdigest()
            assert (
                blob_sha256 == vec["blob_sha256"]
            ), f"AES-GCM SHA256 {vec['id']} failed"


class TestIV:
    """Test IV generation, extraction, and metadata functions."""

    def test_generate_iv_length(self):
        """Test that generate_iv produces correct length IV."""
        iv = generate_iv()
        assert len(iv) == IV_LENGTH
        assert isinstance(iv, bytes)

    def test_generate_iv_with_device_id_and_counter(self):
        """generate_iv with device_id and counter: deterministic prefix and counter."""
        device_id = "device_123"
        counter = 12345
        iv1 = generate_iv(device_id=device_id, counter=counter)
        iv2 = generate_iv(device_id=device_id, counter=counter)
        assert iv1[:8] == iv2[:8]
        assert len(iv1) == IV_LENGTH

    def test_generate_iv_different_device_ids_produce_different_ivs(self):
        """Test that different device IDs produce different IVs."""
        iv1 = generate_iv(device_id="device_1", counter=1000)
        iv2 = generate_iv(device_id="device_2", counter=1000)
        assert iv1 != iv2

    def test_generate_iv_different_counters_produce_different_ivs(self):
        """Test that different counters produce different IVs."""
        iv1 = generate_iv(device_id="device_1", counter=1000)
        iv2 = generate_iv(device_id="device_1", counter=2000)
        assert iv1 != iv2

    def test_generate_iv_fallback_to_random(self):
        """Test that generate_iv falls back to random when no device_id/counter."""
        iv1 = generate_iv()
        iv2 = generate_iv()
        assert iv1 != iv2

    def test_extract_iv_from_blob(self):
        """Test that extract_iv correctly extracts IV from blob."""
        key = bytes.fromhex(
            "d51374d1cbb810c65c46e7df84e87b548e7922e1f90eadeaa9c1838752d23fbe"
        )
        plaintext = b"test message"
        user_id = "usr_01"
        item_id = "itm_01"
        service_name = "GitHub"

        blob = encrypt(plaintext, key, user_id, item_id, service_name)
        import base64

        blob_bytes = base64.b64decode(blob)

        expected_iv = blob_bytes[1 : 1 + IV_LENGTH]
        extracted_iv = extract_iv(blob)

        assert extracted_iv == expected_iv
        assert len(extracted_iv) == IV_LENGTH

    def test_extract_iv_invalid_blob(self):
        """Test that extract_iv rejects unsupported blob versions."""
        with pytest.raises(ValueError, match="Blob too short"):
            extract_iv("AQ==")  # Too short base64

        import base64

        blob_wrong_version = base64.b64encode(b"\x02" + b"\x00" * 20).decode()
        with pytest.raises(ValueError, match="Unsupported blob version"):
            extract_iv(blob_wrong_version)

    def test_get_iv_origin_metadata_random(self):
        """Test that get_iv_origin_metadata correctly parses a random IV."""
        iv = get_iv_origin_metadata(os.urandom(IV_LENGTH))
        assert "device_prefix" in iv
        assert "counter" in iv
        assert "timestamp" in iv
        assert "random" in iv
        assert "raw" in iv
        assert isinstance(iv["device_prefix"], bytes)
        assert isinstance(iv["counter"], int | None)
        assert isinstance(iv["timestamp"], int | None)
        assert isinstance(iv["random"], bytes)
        assert isinstance(iv["raw"], bytes)

    def test_get_iv_origin_metadata_device_counter(self):
        """Test that get_iv_origin_metadata identifies device/counter IVs."""
        device_prefix = b"abcd"
        counter_bytes = (12345).to_bytes(4, byteorder="big")
        random_bytes = b"efgh"
        iv = device_prefix + counter_bytes + random_bytes

        metadata = get_iv_origin_metadata(iv)
        assert isinstance(metadata, dict)
        assert "origin" in metadata
        assert "device_id" in metadata
        assert "counter" in metadata
        assert "timestamp" in metadata

    def test_get_iv_origin_metadata_invalid_length(self):
        """Test that get_iv_origin_metadata handles wrong length IV."""
        with pytest.raises(ValueError, match="IV must be"):
            get_iv_origin_metadata(b"too short")

        with pytest.raises(ValueError, match="IV must be"):
            get_iv_origin_metadata(b"x" * (IV_LENGTH + 1))
