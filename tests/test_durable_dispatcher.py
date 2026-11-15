"""The dispatcher starts one durable execution, named by its job ID, for each queued job."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _module_loading import load_module

_HANDLER = Path(__file__).resolve().parents[1] / "deploy" / "aws" / "lambda" / "durable_dispatcher"


class _FakeLambda:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"StatusCode": 202}


@pytest.fixture()
def dispatch(monkeypatch: Any) -> tuple[Any, _FakeLambda]:
    import boto3

    module = load_module("durable_dispatcher", _HANDLER / "handler.py")
    monkeypatch.setattr(module, "PIPELINE_FUNCTION", "pipeline")
    fake = _FakeLambda()
    monkeypatch.setattr(boto3, "client", lambda *_a, **_kw: fake)
    return module, fake


@pytest.mark.protects("job-dispatched-once")
def test_one_record_starts_one_execution_named_by_its_job(dispatch: tuple[Any, Any]) -> None:
    module, fake = dispatch
    body = {"job_id": "j1", "payload": {"intent": "x"}}

    module.handler({"Records": [{"messageId": "m1", "body": json.dumps(body)}]}, None)

    assert fake.calls == [
        {
            "FunctionName": "pipeline",
            "InvocationType": "Event",
            "Payload": json.dumps(body),
            "DurableExecutionName": "j1",
        }
    ]


@pytest.mark.protects("job-dispatched-once")
def test_a_record_with_no_job_id_raises(dispatch: tuple[Any, Any]) -> None:
    module, fake = dispatch

    with pytest.raises(ValueError):
        module.handler({"Records": [{"messageId": "m1", "body": json.dumps({})}]}, None)
    assert fake.calls == []
