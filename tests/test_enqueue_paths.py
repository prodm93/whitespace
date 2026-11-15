"""Upload keys at the enqueue function: a job may name only the caller's own uploads."""

from __future__ import annotations

import json
from typing import Any

import pytest
from _enqueue_helpers import _auth_event, _fake_boto3, _patch, _paths, enqueue_handler
from _upload_key_cases import NOT_A_LIST, NOT_OWNED_KEYS, OWN_KEY


@pytest.mark.protects("upload-key-owner-only")
def test_a_list_of_own_keys_is_owned() -> None:
    assert _paths.owned_keys([OWN_KEY], "user_a") is True


@pytest.mark.parametrize("path", NOT_OWNED_KEYS)
@pytest.mark.protects("upload-key-owner-only")
def test_a_list_with_any_other_key_is_not_owned(path: object) -> None:
    assert _paths.owned_keys([path], "user_a") is False


@pytest.mark.protects("upload-key-owner-only")
def test_an_empty_list_is_owned() -> None:
    assert _paths.owned_keys([], "user_a") is True


@pytest.mark.parametrize("paths", NOT_A_LIST + [[1]], ids=["string", "none", "int-item"])
@pytest.mark.protects("upload-key-owner-only")
def test_anything_but_a_list_of_strings_is_not_owned(paths: object) -> None:
    assert _paths.owned_keys(paths, "user_a") is False


@pytest.mark.parametrize("field", ["profile_paths", "doc_paths"])
@pytest.mark.protects("upload-key-owner-only")
def test_a_foreign_key_is_refused_before_any_aws_call(monkeypatch: Any, field: str) -> None:
    fb = _fake_boto3()
    _patch(monkeypatch, fb)
    body = {"intent": "run gap analysis", field: ["uploads/user_b/x.pdf"]}

    response = enqueue_handler.handler(_auth_event("user_a", "free", body), None)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {"error": "Invalid upload path"}
    assert fb.resource.call_count == 0
    assert fb.client.call_count == 0


@pytest.mark.protects("upload-key-owner-only")
def test_own_keys_are_enqueued(monkeypatch: Any) -> None:
    fb = _fake_boto3()
    _patch(monkeypatch, fb)
    body = {
        "intent": "run gap analysis",
        "profile_paths": ["uploads/user_a/cv.pdf"],
        "doc_paths": ["uploads/user_a/paper.pdf"],
    }

    response = enqueue_handler.handler(_auth_event("user_a", "free", body), None)

    assert response["statusCode"] == 200
    message = json.loads(fb.client.return_value.send_message.call_args.kwargs["MessageBody"])
    assert message["payload"]["profile_paths"] == ["uploads/user_a/cv.pdf"]
    assert message["payload"]["doc_paths"] == ["uploads/user_a/paper.pdf"]
