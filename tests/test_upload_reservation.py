"""Tests for the upload_url Lambda's atomic reservation logic.

Validates that:
- Reserving a slot increments the counter and creates a record.
- The limit is enforced: reserving beyond max_files fails.
- Expired pending reservations are reclaimed before counting.
- Size and auth limits are enforced.
- The file name is cleaned before it becomes part of the key.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from typing import Any

import pytest

_UPLOADS_RULE = (
    Path(__file__).resolve().parent.parent
    / "deploy"
    / "aws"
    / "lambda"
    / "pipeline_orchestrator"
    / "_uploads.py"
)


def _make_event(user_id: str, tier: str, filename: str, file_size: int) -> dict:
    return {
        "requestContext": {
            "authorizer": {"lambda": {"user_id": user_id, "tier": tier}},
        },
        "body": json.dumps({"filename": filename, "file_size": file_size}),
    }


def test_reserve_increments_counter(upload_url_handler, fake_dynamo):
    event = _make_event("user1", "free", "doc.pdf", 1024)
    resp = upload_url_handler.handler(event, None)
    assert resp["statusCode"] == 200

    usage = fake_dynamo.tables["test-usage"].get("user1", {})
    assert usage.get("active_file_count") == 1


@pytest.mark.protects("upload-size-and-count-limited")
def test_limit_enforced(upload_url_handler, fake_dynamo):
    for i in range(3):
        event = _make_event("user1", "free", f"doc{i}.pdf", 1024)
        resp = upload_url_handler.handler(event, None)
        assert resp["statusCode"] == 200

    event = _make_event("user1", "free", "doc3.pdf", 1024)
    resp = upload_url_handler.handler(event, None)
    assert resp["statusCode"] == 403
    assert "File limit" in json.loads(resp["body"])["error"]


def test_expired_reservations_reclaimed(upload_url_handler, fake_dynamo):
    for i in range(3):
        event = _make_event("user1", "free", f"doc{i}.pdf", 1024)
        upload_url_handler.handler(event, None)

    for _key, record in list(fake_dynamo.tables["test-reservations"].items()):
        record["expires_at"] = int(time.time()) - 60

    event = _make_event("user1", "free", "doc_new.pdf", 1024)
    resp = upload_url_handler.handler(event, None)
    assert resp["statusCode"] == 200

    usage = fake_dynamo.tables["test-usage"]["user1"]
    assert usage["active_file_count"] == 1


@pytest.mark.protects("upload-size-and-count-limited")
def test_size_limit_enforced(upload_url_handler):
    event = _make_event("user1", "free", "big.pdf", 100 * 1024 * 1024)
    resp = upload_url_handler.handler(event, None)
    assert resp["statusCode"] == 403
    assert "MB limit" in json.loads(resp["body"])["error"]


@pytest.mark.protects("caller-id-from-authoriser-only")
def test_unauthenticated_rejected(upload_url_handler):
    event = {"requestContext": {}, "body": "{}"}
    resp = upload_url_handler.handler(event, None)
    assert resp["statusCode"] == 401


@pytest.mark.protects("upload-key-under-caller-prefix")
def test_user_id_in_s3_key(upload_url_handler):
    event = _make_event("user-xyz", "standard", "cv.pdf", 1024)
    body = json.loads(upload_url_handler.handler(event, None)["body"])
    assert "user-xyz" in body["s3_key"]


def test_presign_failure_releases_slot(upload_url_handler, fake_dynamo, _mock_boto3):
    s3_mock = _mock_boto3.client("s3")
    s3_mock.generate_presigned_post.side_effect = Exception("signing error")

    event = _make_event("user1", "free", "doc.pdf", 1024)
    resp = upload_url_handler.handler(event, None)
    assert resp["statusCode"] == 500

    usage = fake_dynamo.tables.get("test-usage", {}).get("user1", {})
    assert usage.get("active_file_count", 0) == 0


@pytest.mark.parametrize(
    ("name", "cleaned"),
    [
        ("cv.pdf", "cv.pdf"),
        ("a/b/cv.pdf", "cv.pdf"),
        ("a\\b\\cv.pdf", "cv.pdf"),
        ("a/../cv.pdf", "cv.pdf"),
        ("/cv.pdf", "cv.pdf"),
        ("", "upload"),
        (".", "upload"),
        ("..", "upload"),
        ("a/", "upload"),
        ("a/..", "upload"),
        (None, "upload"),
        (7, "upload"),
    ],
)
@pytest.mark.protects("upload-key-under-caller-prefix")
def test_clean_filename_keeps_only_a_usable_last_part(
    upload_url_handler: Any, name: object, cleaned: str
) -> None:
    assert upload_url_handler._clean_filename(name) == cleaned


@pytest.mark.protects("upload-key-under-caller-prefix")
def test_a_file_name_with_a_path_gets_a_key_the_pipeline_accepts(upload_url_handler: Any) -> None:
    spec = importlib.util.spec_from_file_location("pipeline_uploads_rule", _UPLOADS_RULE)
    rule = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rule)

    event = _make_event("user1", "free", "a/../b.pdf", 1024)
    body = json.loads(upload_url_handler.handler(event, None)["body"])

    assert rule.owned_key(body["s3_key"], "user1")
