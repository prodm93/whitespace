"""Tests for the tenant ID check."""

from __future__ import annotations

import pytest

from whitespace.tenant import TenantIdError, require_tenant_id

VALID_IDS = ["user_2abcDEF123", "a-b_C9"]

INVALID_IDS = ["", "default", "a#b", "a/b", "a b", "ü", "a\nb", "user_a ", "../x", "a.b"]


@pytest.mark.parametrize("tenant_id", VALID_IDS)
def test_valid_tenant_id_is_returned_unchanged(tenant_id: str) -> None:
    assert require_tenant_id(tenant_id) == tenant_id


@pytest.mark.parametrize("tenant_id", INVALID_IDS)
def test_invalid_tenant_id_is_refused(tenant_id: str) -> None:
    with pytest.raises(TenantIdError):
        require_tenant_id(tenant_id)
