from __future__ import annotations

from typing import Any, cast

import pytest

from app.modules.router import api_router

pytestmark = pytest.mark.integration


def test_auth_router_mounted() -> None:
    paths = [cast(Any, r).path for r in api_router.routes if hasattr(r, "path")]
    assert "/api/v1/auth/ping" in paths
    assert "/api/v1/auth/login/options" in paths
    assert "/api/v1/auth/login/verify" in paths
