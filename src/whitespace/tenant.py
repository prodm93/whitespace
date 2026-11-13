"""Validation of the tenant ID that scopes stored data and the graph namespace.

The allowed characters are Graphiti's own ``group_id`` rule. They exclude ``#``, which
separates the parts of a DynamoDB partition key.
"""

from __future__ import annotations

import re

_TENANT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
_SHARED_NAMESPACE = "default"


class TenantIdError(ValueError):
    """Raised when a tenant ID is empty, shared or malformed."""


def require_tenant_id(value: str) -> str:
    """Return ``value`` unchanged when it is a usable tenant ID, else raise.

    A usable ID matches ``^[A-Za-z0-9_-]+$`` in full and is not the shared BYOK
    namespace ``"default"``.
    """
    if value == _SHARED_NAMESPACE or not _TENANT_ID_PATTERN.fullmatch(value):
        raise TenantIdError(f"Invalid tenant ID: {value!r}")
    return value
