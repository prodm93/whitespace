"""Tests for enqueue handler: auth context extraction and usage enforcement."""

from __future__ import annotations

import json
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from _enqueue_helpers import _auth_event, _fake_boto3, _patch, enqueue_handler
from botocore.exceptions import ClientError

# --- Auth ---


def test_returns_401_without_user_id(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    event = {
        "requestContext": {"authorizer": {"lambda": {"tier": "free"}}},
        "body": json.dumps({"intent": "run"}),
    }
    assert enqueue_handler.handler(event, None)["statusCode"] == 401


def test_reads_user_id_from_auth(monkeypatch: Any) -> None:
    fb = _fake_boto3()
    _patch(monkeypatch, fb)
    enqueue_handler.handler(_auth_event("user-abc", "free"), None)
    msg = json.loads(fb.client.return_value.send_message.call_args.kwargs["MessageBody"])
    assert msg["payload"]["user_id"] == "user-abc"


# --- Tier handling ---


def test_rejects_unknown_tier(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "u")
    r = enqueue_handler.handler(_auth_event("u", "platinum"), None)
    assert r["statusCode"] == 403
    assert json.loads(r["body"])["error"] == "Unknown tier: platinum"


@pytest.mark.parametrize("tier", ["free", "pro", "unlimited"])
def test_fails_closed_when_usage_table_empty(monkeypatch: Any, tier: str) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "")
    r = enqueue_handler.handler(_auth_event("u", tier), None)
    assert r["statusCode"] == 500
    assert (
        json.loads(r["body"])["error"] == "Unable to verify account usage. Please try again later."
    )


def test_unlimited_creates_not_required_job(monkeypatch: Any) -> None:
    fb = _fake_boto3()
    _patch(monkeypatch, fb)
    r = enqueue_handler.handler(_auth_event("u-pro", "pro"), None)
    assert r["statusCode"] == 200
    assert not fb.client.return_value.transact_write_items.called
    put = fb.resource.return_value.Table.return_value.put_item
    assert put.call_args.kwargs["Item"]["reservation_status"] == "not_required"


# --- Reservation ---


def test_allows_free_under_cap(monkeypatch: Any) -> None:
    fb = _fake_boto3()
    _patch(monkeypatch, fb)
    assert enqueue_handler.handler(_auth_event("u", "free"), None)["statusCode"] == 200


@pytest.mark.parametrize("tier,limit", [("free", 2), ("standard", 40)])
def test_denies_at_cap(monkeypatch: Any, tier: str, limit: int) -> None:
    fb = _fake_boto3(deny_reserve=True)
    _patch(monkeypatch, fb)
    r = enqueue_handler.handler(_auth_event("u", tier), None)
    assert r["statusCode"] == 429
    assert json.loads(r["body"])["error"] == f"Tier '{tier}' limit of {limit} runs reached"


def test_monthly_reset_allows_standard(monkeypatch: Any) -> None:
    fb = _fake_boto3(stale_reset=True)
    _patch(monkeypatch, fb)
    r = enqueue_handler.handler(_auth_event("u", "standard"), None)
    assert r["statusCode"] == 200
    assert fb.resource.return_value.Table.return_value.update_item.called


def test_monthly_reset_cas_exhaustion_fails_closed(monkeypatch: Any) -> None:
    fb = _fake_boto3(stale_reset=True)
    cas_err = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
        "UpdateItem",
    )
    fb.resource.return_value.Table.return_value.update_item.side_effect = cas_err
    _patch(monkeypatch, fb)
    r = enqueue_handler.handler(_auth_event("u", "standard"), None)
    assert r["statusCode"] == 500
    assert "Unable to verify" in json.loads(r["body"])["error"]


def test_monthly_reset_cas_retry_succeeds(monkeypatch: Any) -> None:
    fb = _fake_boto3(stale_reset=True)
    calls = [0]

    def _update(**kw: Any) -> None:
        calls[0] += 1
        if calls[0] < 2:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
                "UpdateItem",
            )

    fb.resource.return_value.Table.return_value.update_item.side_effect = _update
    _patch(monkeypatch, fb)
    r = enqueue_handler.handler(_auth_event("u", "standard"), None)
    assert r["statusCode"] == 200
