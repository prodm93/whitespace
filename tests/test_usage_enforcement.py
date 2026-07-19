"""Tests for authoriser context extraction (A8) and usage preflight (A6).

A8: both lambda handlers read user_id and tier from
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

# Load handlers under distinct module names to avoid collision with
# the pipeline_orchestrator handler on sys.path (test_saas_orchestrator
# puts that directory first).
_ROOT = Path(__file__).parent.parent

_enqueue_spec = importlib.util.spec_from_file_location(
    "enqueue_handler",
    _ROOT / "deploy" / "aws" / "lambda" / "orchestrate_enqueue" / "handler.py",
)
enqueue_handler = importlib.util.module_from_spec(_enqueue_spec)
_enqueue_spec.loader.exec_module(enqueue_handler)  # type: ignore[union-attr]

_upload_spec = importlib.util.spec_from_file_location(
    "upload_handler",
    _ROOT / "deploy" / "aws" / "lambda" / "upload_url" / "handler.py",
)
upload_handler = importlib.util.module_from_spec(_upload_spec)
_upload_spec.loader.exec_module(upload_handler)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    """user_id is taken from requestContext.authorizer.lambda.user_id."""
    fb = _fake_boto3(run_count=0)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    enqueue_handler.handler(_auth_event("user-abc", "free"), None)

    put_item_call = fb.resource.return_value.Table.return_value.put_item.call_args
    assert put_item_call.kwargs["Item"]["user_id"] == "user-abc"


def test_enqueue_reads_tier_from_lambda_key(monkeypatch: Any) -> None:
    """tier is taken from requestContext.authorizer.lambda.tier; pro skips DynamoDB."""
    fb = MagicMock()
    fb.resource.return_value.Table.return_value.put_item = MagicMock()
    fb.client.return_value.send_message = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-pro", "pro"), None)

    assert result["statusCode"] == 200
    assert not fb.resource.return_value.Table.return_value.get_item.called


def test_upload_url_reads_user_id_from_lambda_key(monkeypatch: Any) -> None:
    """upload_url handler reads user_id from requestContext.authorizer.lambda.user_id."""
    fb = MagicMock()
    fb.client.return_value.list_objects_v2.return_value = {"KeyCount": 0}
    fb.client.return_value.generate_presigned_post.return_value = {
        "url": "https://s3.example.com",
        "fields": {},
    }
    monkeypatch.setitem(sys.modules, "boto3", fb)

    event = {
        "requestContext": {"authorizer": {"lambda": {"user_id": "user-xyz", "tier": "standard"}}},
        "body": json.dumps({"filename": "cv.pdf", "file_size": 1024}),
    }
    result = json.loads(upload_handler.handler(event, None)["body"])
    assert "user-xyz" in result["s3_key"]


# ---------------------------------------------------------------------------
# A6: preflight — deny, allow, reset
# ---------------------------------------------------------------------------


def test_preflight_allows_free_tier_under_cap(monkeypatch: Any) -> None:
    """Free-tier user with 1 run is allowed (cap is 2)."""
    fb = _fake_boto3(run_count=1)
    fb.resource.return_value.Table.return_value.put_item = MagicMock()
    fb.client.return_value.send_message = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-1", "free"), None)
    assert result["statusCode"] == 200


def test_preflight_denies_free_tier_at_cap(monkeypatch: Any) -> None:
    """Free-tier user at cap of 2 gets HTTP 429 with the exact middleware error string."""
    fb = _fake_boto3(run_count=2)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-2", "free"), None)
    assert result["statusCode"] == 429
    body = json.loads(result["body"])
    assert body["error"] == "Tier 'free' limit of 2 runs reached"


def test_preflight_denies_standard_tier_at_cap(monkeypatch: Any) -> None:
    """Standard-tier user at cap of 40 (within 30-day window) is denied."""
    stale_ts = int(time.time()) - (5 * 24 * 3600)  # 5 days ago, not yet reset
    fb = _fake_boto3(run_count=40, last_reset_ts=stale_ts)
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")

    result = enqueue_handler.handler(_auth_event("u-3", "standard"), None)
    assert result["statusCode"] == 429
    body = json.loads(result["body"])
    assert body["error"] == "Tier 'standard' limit of 40 runs reached"


def test_preflight_resets_standard_tier_after_30_days(monkeypatch: Any) -> None:
    """Standard-tier user at cap but past 30-day window gets reset and is allowed."""
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
    """Missing user_id from auth context returns 401 before any DynamoDB touch."""
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


def test_preflight_skipped_when_usage_table_empty(monkeypatch: Any) -> None:
    """No USAGE_TABLE configured: preflight is skipped, enqueue proceeds."""
    fb = MagicMock()
    fb.resource.return_value.Table.return_value.put_item = MagicMock()
    fb.client.return_value.send_message = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    monkeypatch.setattr(enqueue_handler, "USAGE_TABLE", "")

    result = enqueue_handler.handler(_auth_event("u-5", "free"), None)
    assert result["statusCode"] == 200
    assert not fb.resource.return_value.Table.return_value.get_item.called


# ---------------------------------------------------------------------------
# upload_url: file count enforcement
# ---------------------------------------------------------------------------


def _upload_event(user_id: str, tier: str, file_size: int = 1024) -> dict:
    return {
        "requestContext": {"authorizer": {"lambda": {"user_id": user_id, "tier": tier}}},
        "body": json.dumps({"filename": "doc.pdf", "file_size": file_size}),
    }


def test_upload_url_denies_at_file_limit(monkeypatch: Any) -> None:
    """Free-tier user with 3 existing files (the cap) gets 403 with the file-limit string."""
    fb = MagicMock()
    fb.client.return_value.list_objects_v2.return_value = {"KeyCount": 3}
    monkeypatch.setitem(sys.modules, "boto3", fb)

    result = upload_handler.handler(_upload_event("u-full", "free"), None)
    assert result["statusCode"] == 403
    body = json.loads(result["body"])
    assert body["error"] == "File limit of 3 files reached for free tier"


def test_upload_url_allows_under_file_limit(monkeypatch: Any) -> None:
    """Free-tier user with 2 existing files is allowed (cap is 3)."""
    fb = MagicMock()
    fb.client.return_value.list_objects_v2.return_value = {"KeyCount": 2}
    fb.client.return_value.generate_presigned_post.return_value = {
        "url": "https://s3.example.com",
        "fields": {},
    }
    monkeypatch.setitem(sys.modules, "boto3", fb)

    result = upload_handler.handler(_upload_event("u-ok", "free"), None)
    assert result["statusCode"] == 200
    assert "s3_key" in json.loads(result["body"])
