"""Tests for authoriser context extraction (A8) and usage preflight (A6).

A8: the enqueue handler reads user_id and tier from
    event["requestContext"]["authorizer"]["lambda"], not from the old
    authorizer.userId / authorizer.tier keys.

A6: orchestrate_enqueue rejects over-limit users before enqueueing
    (HTTP 429, exact middleware error string); pro/unlimited tiers are
    never consulted in DynamoDB; standard/pro counts reset after 30 days.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_ROOT = Path(__file__).parent.parent

_enqueue_spec = importlib.util.spec_from_file_location(
    "enqueue_handler",
    _ROOT / "deploy" / "aws" / "lambda" / "orchestrate_enqueue" / "handler.py",
)
enqueue_handler = importlib.util.module_from_spec(_enqueue_spec)
_enqueue_spec.loader.exec_module(enqueue_handler)  # type: ignore[union-attr]


def _auth_event(user_id: str, tier: str, body: dict | None = None) -> dict:
    return {
        "requestContext": {"authorizer": {"lambda": {"user_id": user_id, "tier": tier}}},
        "body": json.dumps(body or {"intent": "run gap analysis"}),
    }


def _fake_boto3(run_count: int = 0, last_reset_ts: int = 0) -> MagicMock:
    fb = MagicMock()
    item: dict[str, Any] = {"user_id": "u", "run_count": run_count}
    if last_reset_ts:
        item["last_reset_ts"] = last_reset_ts
    fb.resource.return_value.Table.return_value.get_item.return_value = {"Item": item}
    return fb


# ---------------------------------------------------------------------------
# A8: authoriser context extraction
# ---------------------------------------------------------------------------


def test_enqueue_reads_user_id_from_lambda_key(monkeypatch: Any) -> None:
    fb = _fake_boto3(run_count=0)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    enqueue_handler.handler(_auth_event("user-abc", "free"), None)

    put_item_call = fb.resource.return_value.Table.return_value.put_item.call_args
    assert put_item_call.kwargs["Item"]["user_id"] == "user-abc"


def test_enqueue_reads_tier_from_lambda_key(monkeypatch: Any) -> None:
    fb = MagicMock()
    fb.resource.return_value.Table.return_value.put_item = MagicMock()
    fb.client.return_value.send_message = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-pro", "pro"), None)

    assert result["statusCode"] == 200
    assert not fb.resource.return_value.Table.return_value.get_item.called


# ---------------------------------------------------------------------------
# A6: preflight; deny, allow, reset
# ---------------------------------------------------------------------------


def test_preflight_allows_free_tier_under_cap(monkeypatch: Any) -> None:
    fb = _fake_boto3(run_count=1)
    fb.resource.return_value.Table.return_value.put_item = MagicMock()
    fb.client.return_value.send_message = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-1", "free"), None)
    assert result["statusCode"] == 200


def test_preflight_denies_free_tier_at_cap(monkeypatch: Any) -> None:
    fb = _fake_boto3(run_count=2)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-2", "free"), None)
    assert result["statusCode"] == 429
    body = json.loads(result["body"])
    assert body["error"] == "Tier 'free' limit of 2 runs reached"


def test_preflight_denies_standard_tier_at_cap(monkeypatch: Any) -> None:
    stale_ts = int(time.time()) - (5 * 24 * 3600)
    fb = _fake_boto3(run_count=40, last_reset_ts=stale_ts)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-3", "standard"), None)
    assert result["statusCode"] == 429
    body = json.loads(result["body"])
    assert body["error"] == "Tier 'standard' limit of 40 runs reached"


def test_preflight_resets_standard_tier_after_30_days(monkeypatch: Any) -> None:
    stale_ts = int(time.time()) - (31 * 24 * 3600)
    fb = _fake_boto3(run_count=40, last_reset_ts=stale_ts)
    fb.resource.return_value.Table.return_value.update_item = MagicMock()
    fb.resource.return_value.Table.return_value.put_item = MagicMock()
    fb.client.return_value.send_message = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-4", "standard"), None)
    assert result["statusCode"] == 200
    assert fb.resource.return_value.Table.return_value.update_item.called


def test_enqueue_returns_401_without_user_id(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)

    event = {
        "requestContext": {"authorizer": {"lambda": {"tier": "free"}}},
        "body": json.dumps({"intent": "run"}),
    }
    result = enqueue_handler.handler(event, None)
    assert result["statusCode"] == 401
    assert json.loads(result["body"])["error"] == "Unauthenticated"
    assert not fb.resource.called


def test_preflight_fails_closed_when_usage_table_empty_free(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "")

    result = enqueue_handler.handler(_auth_event("u-5", "free"), None)
    assert result["statusCode"] == 500
    body = json.loads(result["body"])
    assert body["error"] == "Unable to verify account usage. Please try again later."
    assert not fb.resource.return_value.Table.return_value.get_item.called


def test_preflight_fails_closed_when_usage_table_empty_pro(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "")

    result = enqueue_handler.handler(_auth_event("u-5b", "pro"), None)
    assert result["statusCode"] == 500
    body = json.loads(result["body"])
    assert body["error"] == "Unable to verify account usage. Please try again later."


def test_preflight_fails_closed_when_usage_table_empty_unlimited(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "")

    result = enqueue_handler.handler(_auth_event("u-5c", "unlimited"), None)
    assert result["statusCode"] == 500
    body = json.loads(result["body"])
    assert body["error"] == "Unable to verify account usage. Please try again later."


def test_preflight_rejects_unknown_tier(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-6", "platinum"), None)
    assert result["statusCode"] == 403
    body = json.loads(result["body"])
    assert body["error"] == "Unknown tier: platinum"
