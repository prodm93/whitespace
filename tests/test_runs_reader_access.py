"""Caller identity and job ownership in the runs_reader Lambda."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from _fake_sessions_table import install_sessions_table
from _runs_reader_helpers import _event, _load

from whitespace.store.base import GapRun
from whitespace.store.dynamo_store import DynamoSessionStore


def _with_user_id(user_id: Any) -> dict:
    return {"requestContext": {"authorizer": {"lambda": {"user_id": user_id}}}}


@pytest.mark.protects("caller-id-from-authoriser-only")
def test_caller_id_is_the_authoriser_user_id() -> None:
    assert _load()._caller_id(_with_user_id("user_a")) == "user_a"


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"requestContext": None},
        {"requestContext": {"authorizer": None}},
        {"requestContext": {"authorizer": {"lambda": None}}},
        _with_user_id(None),
        _with_user_id(7),
        _with_user_id(["user_a"]),
    ],
)
@pytest.mark.protects("caller-id-from-authoriser-only")
def test_caller_id_is_empty_without_a_string_user_id(event: dict) -> None:
    assert _load()._caller_id(event) == ""


@pytest.mark.parametrize(
    ("route", "job_id"), [("GET /api/jobs/{jobId}", "j1"), ("GET /api/runs/latest", None)]
)
@pytest.mark.protects("caller-id-from-authoriser-only")
def test_no_authoriser_context_gives_401_before_any_aws_call(route: str, job_id: Any) -> None:
    fake_boto3 = MagicMock()
    with (
        patch.dict(sys.modules, {"boto3": fake_boto3}),
        patch("whitespace.store.dynamo_store.DynamoSessionStore") as store_class,
    ):
        result = _load().handler(_event(route, job_id, caller=None), None)

    assert result["statusCode"] == 401
    assert json.loads(result["body"]) == {"error": "Unauthenticated"}
    fake_boto3.resource.assert_not_called()
    fake_boto3.client.assert_not_called()
    store_class.assert_not_called()


def _job_status(item: dict | None) -> tuple[dict, MagicMock]:
    """Ask for job ``j1`` as ``user_b`` while the jobs table holds ``item``."""
    fake_boto3 = MagicMock()
    fake_boto3.resource.return_value.Table.return_value.get_item.return_value = {"Item": item}
    with patch.dict(sys.modules, {"boto3": fake_boto3}):
        result = _load().handler(_event("GET /api/jobs/{jobId}", "j1", caller="user_b"), None)
    return result, fake_boto3


_FOREIGN_JOB = {"job_id": "j1", "user_id": "user_a", "result_key": "results/j1.json"}
_JOB_WITHOUT_OWNER = {"job_id": "j1", "result_key": "results/j1.json"}


@pytest.mark.parametrize("item", [_FOREIGN_JOB, _JOB_WITHOUT_OWNER, None])
@pytest.mark.protects("job-status-owner-only")
def test_a_job_the_caller_does_not_own_is_not_found(item: dict | None) -> None:
    result, fake_boto3 = _job_status(item)

    assert result["statusCode"] == 404
    assert json.loads(result["body"]) == {"error": "Job not found"}
    fake_boto3.client.assert_not_called()


@pytest.mark.protects("job-status-owner-only")
def test_the_three_not_found_answers_are_byte_equal() -> None:
    answers = [_job_status(item)[0] for item in (_FOREIGN_JOB, _JOB_WITHOUT_OWNER, None)]

    assert answers[0] == answers[1] == answers[2]


@pytest.mark.protects("latest-run-owner-only")
def test_the_latest_run_of_another_user_is_never_returned(monkeypatch: Any) -> None:
    install_sessions_table(monkeypatch)
    gap_run = GapRun(run_id="gap-a", timestamp=datetime(2026, 7, 1, tzinfo=UTC), domain="x")
    asyncio.run(DynamoSessionStore("sessions", "us-east-1", owner="user_a").save_gap_run(gap_run))
    handler = _load().handler

    as_b = handler(_event("GET /api/runs/latest", caller="user_b"), None)
    as_a = handler(_event("GET /api/runs/latest", caller="user_a"), None)

    assert json.loads(as_b["body"]) == {"gap_run": None, "idea_runs": []}
    assert json.loads(as_a["body"])["gap_run"]["run_id"] == "gap-a"
