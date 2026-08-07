"""Tests for the upload_confirm Lambda handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from _fake_dynamodb import _TransactionCancelled


def _make_upload_event(user_id: str, tier: str, filename: str) -> dict:
    return {
        "requestContext": {
            "authorizer": {"lambda": {"user_id": user_id, "tier": tier}},
        },
        "body": json.dumps({"filename": filename, "file_size": 1024}),
    }


def _s3_event(s3_key: str, event_name: str = "ObjectCreated:Post") -> dict:
    return {
        "Records": [
            {"s3": {"object": {"key": s3_key}}, "eventName": event_name},
        ],
    }


def _reserve(url_h, confirm_h=None, filename: str = "doc.pdf") -> str:
    resp = url_h.handler(_make_upload_event("user1", "free", filename), None)
    s3_key = json.loads(resp["body"])["s3_key"]
    if confirm_h:
        confirm_h.handler(_s3_event(s3_key), None)
    return s3_key


def test_confirm_transitions_to_confirmed(
    upload_url_handler,
    upload_confirm_handler,
    fake_dynamo,
):
    s3_key = _reserve(upload_url_handler)

    reservation = fake_dynamo.tables["test-reservations"][s3_key]
    assert reservation["status"] == "pending"
    assert "expires_at" in reservation

    upload_confirm_handler.handler(_s3_event(s3_key), None)

    reservation = fake_dynamo.tables["test-reservations"][s3_key]
    assert reservation["status"] == "confirmed"
    assert "expires_at" not in reservation


def test_confirmed_not_reclaimed(
    upload_url_handler,
    upload_confirm_handler,
    fake_dynamo,
):
    for i in range(3):
        _reserve(upload_url_handler, upload_confirm_handler, f"doc{i}.pdf")

    resp = upload_url_handler.handler(
        _make_upload_event("user1", "free", "doc3.pdf"),
        None,
    )
    assert resp["statusCode"] == 403

    usage = fake_dynamo.tables["test-usage"]["user1"]
    assert usage["active_file_count"] == 3


def test_confirmation_fallback_uses_consistent_read(
    upload_url_handler,
    upload_confirm_handler,
    fake_dynamo,
):
    s3_key = _reserve(upload_url_handler, upload_confirm_handler)

    calls: list[dict] = []
    original = fake_dynamo.get_item

    def _tracking_get(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    fake_dynamo.get_item = _tracking_get
    upload_confirm_handler.handler(_s3_event(s3_key), None)
    fake_dynamo.get_item = original

    assert any(c.get("ConsistentRead") is True for c in calls)


def test_orphaned_upload_deleted(
    upload_url_handler,
    upload_confirm_handler,
    fake_dynamo,
    _mock_boto3,
):
    s3_key = _reserve(upload_url_handler)

    fake_dynamo.tables["test-reservations"].pop(s3_key, None)
    fake_dynamo.tables["test-usage"]["user1"]["active_file_count"] = 0

    upload_confirm_handler.handler(_s3_event(s3_key), None)

    assert s3_key not in fake_dynamo.tables["test-reservations"]
    assert fake_dynamo.tables["test-usage"]["user1"]["active_file_count"] == 0

    s3_mock = _mock_boto3.client("s3")
    s3_mock.delete_object.assert_called_once_with(
        Bucket="test-uploads",
        Key=s3_key,
    )


def test_orphan_deletion_failure_propagates(
    upload_url_handler,
    upload_confirm_handler,
    fake_dynamo,
    _mock_boto3,
):
    s3_key = _reserve(upload_url_handler)

    fake_dynamo.tables["test-reservations"].pop(s3_key, None)
    fake_dynamo.tables["test-usage"]["user1"]["active_file_count"] = 0

    s3_mock = _mock_boto3.client("s3")
    s3_mock.delete_object.side_effect = Exception("S3 error")

    with pytest.raises(Exception, match="S3 error"):
        upload_confirm_handler.handler(_s3_event(s3_key), None)


def test_lifecycle_delete_decrements_and_idempotent(
    upload_url_handler,
    upload_confirm_handler,
    fake_dynamo,
):
    s3_key = _reserve(upload_url_handler, upload_confirm_handler)
    assert fake_dynamo.tables["test-usage"]["user1"]["active_file_count"] == 1

    upload_confirm_handler.handler(
        _s3_event(s3_key, "LifecycleExpiration:Delete"),
        None,
    )
    assert s3_key not in fake_dynamo.tables["test-reservations"]
    assert fake_dynamo.tables["test-usage"]["user1"]["active_file_count"] == 0

    upload_confirm_handler.handler(
        _s3_event(s3_key, "LifecycleExpiration:Delete"),
        None,
    )
    assert fake_dynamo.tables["test-usage"]["user1"]["active_file_count"] == 0


def test_lifecycle_non_conditional_failure_propagates(
    upload_url_handler,
    upload_confirm_handler,
    fake_dynamo,
):
    s3_key = _reserve(upload_url_handler, upload_confirm_handler)

    original = fake_dynamo.transact_write_items

    def _fail_with_capacity_error(**kwargs: MagicMock) -> None:
        reasons = [{"Code": "ProvisionedThroughputExceeded"}]
        raise _TransactionCancelled("capacity exceeded", reasons)

    fake_dynamo.transact_write_items = _fail_with_capacity_error

    with pytest.raises(_TransactionCancelled, match="capacity exceeded"):
        upload_confirm_handler.handler(
            _s3_event(s3_key, "LifecycleExpiration:Delete"),
            None,
        )

    fake_dynamo.transact_write_items = original


def test_lifecycle_delete_no_reservation(
    upload_confirm_handler,
    fake_dynamo,
):
    upload_confirm_handler.handler(
        _s3_event(
            "uploads/user1/unknown_file.pdf",
            "LifecycleExpiration:Delete",
        ),
        None,
    )
    assert fake_dynamo.tables.get("test-usage", {}).get("user1") is None
