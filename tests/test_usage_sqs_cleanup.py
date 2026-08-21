"""Tests for SQS failure cleanup in the enqueue handler."""

from __future__ import annotations

from typing import Any

import pytest
from _enqueue_helpers import _auth_event, _fake_boto3, _patch, enqueue_handler
from botocore.exceptions import ClientError


def test_cleanup_rollback_on_sqs_failure(monkeypatch: Any) -> None:
    fb = _fake_boto3()
    sqs_err = ClientError(
        {"Error": {"Code": "ServiceException", "Message": "SQS down"}},
        "SendMessage",
    )
    fb.client.return_value.send_message.side_effect = sqs_err
    _patch(monkeypatch, fb)
    with pytest.raises(ClientError):
        enqueue_handler.handler(_auth_event("u", "free"), None)
    assert fb.client.return_value.transact_write_items.call_count == 2


def test_cleanup_deletes_job_for_unlimited(monkeypatch: Any) -> None:
    fb = _fake_boto3()
    sqs_err = ClientError(
        {"Error": {"Code": "ServiceException", "Message": "SQS down"}},
        "SendMessage",
    )
    fb.client.return_value.send_message.side_effect = sqs_err
    _patch(monkeypatch, fb)
    with pytest.raises(ClientError):
        enqueue_handler.handler(_auth_event("u", "pro"), None)
    fb.resource.return_value.Table.return_value.delete_item.assert_called_once()
