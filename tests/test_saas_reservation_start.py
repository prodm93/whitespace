"""Pipeline reservation start, ownership, and replay tests."""

from __future__ import annotations

import sys
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from _saas_helpers import FakeDurableContext, _evt
from botocore.exceptions import ClientError


def _conditional_failure() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
        "UpdateItem",
    )


def test_claim_lease_is_25_hours() -> None:
    import _reservation_state

    assert _reservation_state._CLAIM_TTL_SECONDS == 25 * 3600


def test_start_requires_unexpired_reservation(monkeypatch: Any) -> None:
    import _reservation_state

    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "jobs")

    assert _reservation_state._validate_and_start("j1", "u1") == "required"

    call = fb.resource.return_value.Table.return_value.update_item.call_args
    assert "reservation_expires_at > :now" in call.kwargs["ConditionExpression"]
    assert ":now" in call.kwargs["ExpressionAttributeValues"]


@pytest.mark.parametrize(
    ("reservation_status", "job_status"),
    [("pending", "pending"), ("claimed", "running")],
)
def test_owned_expired_reservation_is_rejected(
    monkeypatch: Any,
    reservation_status: str,
    job_status: str,
) -> None:
    import _reservation_state

    fb = MagicMock()
    table = fb.resource.return_value.Table.return_value
    table.update_item.side_effect = _conditional_failure()
    table.get_item.return_value = {
        "Item": {
            "user_id": "u1",
            "status": job_status,
            "reservation_status": reservation_status,
            "reservation_expires_at": int(time.time()) - 1,
        }
    }
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "jobs")

    assert _reservation_state._validate_and_start("j1", "u1") == "owned_expired"


def test_owned_expired_reservation_is_released_and_failed(monkeypatch: Any) -> None:
    import _reservation_state
    import handler

    cleanup = MagicMock()
    set_status = MagicMock()
    monkeypatch.setattr(
        handler,
        "_validate_and_start",
        MagicMock(return_value="owned_expired"),
    )
    monkeypatch.setattr(handler, "_cleanup_reservation", cleanup)
    monkeypatch.setattr(handler, "_set_status", set_status)
    ctx = FakeDurableContext()

    with pytest.raises(_reservation_state.ReservationStateError):
        handler.handler(_evt("j7", "Run gaps", user_id="u1"), ctx)

    cleanup.assert_called_once_with("u1", "j7")
    set_status.assert_called_once_with("j7", "failed", error=_reservation_state._USER_FACING_ERROR)
    assert "cleanup_expired_reservation" in ctx.step_calls
    assert "status_failed" in ctx.step_calls


def test_missing_job_row_raises_without_mutation(monkeypatch: Any) -> None:
    import _reservation_state
    import handler

    fb = MagicMock()
    fb.resource.return_value.Table.return_value.update_item.side_effect = _conditional_failure()
    fb.resource.return_value.Table.return_value.get_item.return_value = {}
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "jobs")
    ctx = FakeDurableContext()

    with pytest.raises(_reservation_state.ReservationStateError):
        handler.handler(_evt("j8", "Run gaps", user_id="u1"), ctx)

    assert "status_failed" not in ctx.step_calls


def test_identity_mismatch_raises_without_mutation(monkeypatch: Any) -> None:
    import _reservation_state
    import handler

    fb = MagicMock()
    fb.resource.return_value.Table.return_value.update_item.side_effect = _conditional_failure()
    fb.resource.return_value.Table.return_value.get_item.return_value = {
        "Item": {"reservation_status": "pending", "user_id": "other_user"}
    }
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(_reservation_state, "_JOBS_TABLE", "jobs")
    ctx = FakeDurableContext()

    with pytest.raises(_reservation_state.ReservationStateError):
        handler.handler(_evt("j9", "Run gaps", user_id="u1"), ctx)

    assert "status_failed" not in ctx.step_calls
