"""Upload keys in the pipeline function: only the caller's own uploads are read."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from _runtime_helpers import use_factory
from _saas_helpers import (
    FakeDurableContext,
    FakePipeline,
    FakeStore,
    _evt,
    _handler_boto3,
    install_runtime,
)
from _upload_key_cases import NOT_A_LIST, NOT_OWNED_KEYS, OWN_KEY


@pytest.mark.protects("upload-key-owner-only")
def test_an_own_upload_key_is_owned() -> None:
    from _uploads import owned_key

    assert owned_key(OWN_KEY, "user_a") is True


@pytest.mark.parametrize("path", NOT_OWNED_KEYS)
@pytest.mark.protects("upload-key-owner-only")
def test_any_other_key_or_local_path_is_not_owned(path: object) -> None:
    from _uploads import owned_key

    assert owned_key(path, "user_a") is False


@pytest.mark.protects("upload-key-owner-only")
async def test_a_foreign_key_is_refused_before_any_download(monkeypatch: Any) -> None:
    from _uploads import UploadPathError, localise_paths

    boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", boto3)

    with pytest.raises(UploadPathError, match="^Invalid upload path$"):
        await localise_paths([OWN_KEY, "uploads/user_b/abc_cv.pdf"], "user_a")
    assert boto3.client.return_value.download_file.call_count == 0


@pytest.mark.protects("upload-key-owner-only")
async def test_an_own_key_is_downloaded_into_the_tenant_directory(monkeypatch: Any) -> None:
    from _uploads import localise_paths

    boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", boto3)

    [local] = await localise_paths([OWN_KEY], "user_a")

    assert local.startswith("/tmp/whitespace/user_a/")
    boto3.client.return_value.download_file.assert_called_once()
    assert boto3.client.return_value.download_file.call_args.args[1:] == (OWN_KEY, local)


@pytest.mark.parametrize("field", ["profile_paths", "doc_paths"])
@pytest.mark.protects("upload-key-owner-only")
@pytest.mark.protects("run-slot-returned-on-failure")
def test_a_job_that_names_a_foreign_upload_fails_before_the_run_opens(
    monkeypatch: Any, request: Any, field: str
) -> None:
    import _failure
    import _runtime
    import handler

    install_runtime(monkeypatch, FakePipeline(), FakeStore(), request)
    factory = use_factory(monkeypatch, _runtime)
    boto3 = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    monkeypatch.setattr(handler, "_validate_and_start", lambda _jid, _uid: "required")
    monkeypatch.setattr(handler, "_validate_usage_config", lambda: None)
    open_run = MagicMock()
    publish = MagicMock()
    cleanup = MagicMock()
    set_status = MagicMock()
    monkeypatch.setattr(handler, "open_run", open_run)
    monkeypatch.setattr(handler, "_publish", publish)
    monkeypatch.setattr(_failure, "_cleanup_reservation", cleanup)
    monkeypatch.setattr(_failure, "_set_status", set_status)
    ctx = FakeDurableContext()
    event = _evt("j1", "Run gaps", user_id="u1", **{field: ["uploads/u2/cv.pdf"]})

    with pytest.raises(ValueError, match="^Invalid upload path$"):
        handler.handler(event, ctx)

    set_status.assert_called_once_with("j1", "failed", error="Invalid upload path")
    cleanup.assert_called_once_with("u1", "j1")
    assert boto3.client.return_value.download_file.call_count == 0
    publish.assert_not_called()
    assert not [c for c in set_status.call_args_list if "completed" in c.args]
    assert not [n for n in ctx.step_calls if n.startswith("decide-")]
    assert "extract_profile" not in ctx.step_calls
    assert "gap_analysis" not in ctx.step_calls
    open_run.assert_not_called()
    assert factory.built == []


@pytest.mark.protects("upload-key-owner-only")
def test_a_list_of_own_keys_is_owned() -> None:
    from _uploads import owned_keys

    assert owned_keys([OWN_KEY], "user_a") is True
    assert owned_keys([], "user_a") is True


@pytest.mark.parametrize("key", NOT_OWNED_KEYS)
@pytest.mark.protects("upload-key-owner-only")
def test_a_list_with_any_other_key_is_not_owned(key: object) -> None:
    from _uploads import owned_keys

    assert owned_keys([key], "user_a") is False


@pytest.mark.parametrize("paths", NOT_A_LIST + [[1]], ids=["string", "none", "int-item"])
@pytest.mark.protects("upload-key-owner-only")
def test_anything_but_a_list_of_strings_is_not_owned(paths: object) -> None:
    from _uploads import owned_keys

    assert owned_keys(paths, "user_a") is False


@pytest.mark.parametrize(
    "field,value", [("profile_paths", None), ("doc_paths", "uploads/u1/cv.pdf")]
)
@pytest.mark.protects("upload-key-owner-only")
def test_a_job_whose_upload_field_is_not_a_list_fails_before_the_run_opens(
    monkeypatch: Any, request: Any, field: str, value: object
) -> None:
    import _failure
    import _runtime
    import handler

    install_runtime(monkeypatch, FakePipeline(), FakeStore(), request)
    factory = use_factory(monkeypatch, _runtime)
    boto3 = _handler_boto3(with_reservation=True)
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    monkeypatch.setattr(handler, "_validate_and_start", lambda _jid, _uid: "required")
    monkeypatch.setattr(handler, "_validate_usage_config", lambda: None)
    open_run = MagicMock()
    cleanup = MagicMock()
    set_status = MagicMock()
    monkeypatch.setattr(handler, "open_run", open_run)
    monkeypatch.setattr(_failure, "_cleanup_reservation", cleanup)
    monkeypatch.setattr(_failure, "_set_status", set_status)
    event = {"job_id": "j1", "payload": {"intent": "Run gaps", "user_id": "u1", field: value}}

    with pytest.raises(ValueError, match="^Invalid upload path$"):
        handler.handler(event, FakeDurableContext())

    set_status.assert_called_once_with("j1", "failed", error="Invalid upload path")
    cleanup.assert_called_once_with("u1", "j1")
    open_run.assert_not_called()
    assert boto3.client.return_value.download_file.call_count == 0
    assert factory.built == []
