from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.vault.schemas import VaultCreateRequest, VaultUpdateRequest


def test_vault_create_request_rejects_malformed_base64_blob() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VaultCreateRequest(
            service_name="Example",
            login_name="user",
            password_blob="%%%not-base64%%%",
            notes_blob="dGVzdA==",
        )

    assert "malformed or non-base64 blob" in str(exc_info.value)


def test_vault_update_request_rejects_malformed_base64_blob() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VaultUpdateRequest(password_blob="%%%not-base64%%%")

    assert "malformed or non-base64 blob" in str(exc_info.value)
