"""Tests for the runs_reader Lambda handler (A1).

Loaded via importlib file path to avoid colliding with
pipeline_orchestrator/handler.py on sys.path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.store.base import GapRun, IdeaRun

_HANDLER_PATH = (
    Path(__file__).parent.parent / "deploy" / "aws" / "lambda" / "runs_reader" / "handler.py"
)


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("runs_reader_handler", _HANDLER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _event(route: str, job_id: str | None = None) -> dict:
    return {
        "routeKey": route,
        "pathParameters": {"jobId": job_id} if job_id else None,
    }


def _need(title: str) -> UnmetNeed:
    return UnmetNeed(title=title, description="d", current_state="c", why_unmet="w")


def _proposal(title: str) -> IdeationProposal:
    return IdeationProposal(
        title=title,
        problem_statement="p",
        technical_approach="t",
        why_this_person="y",
        differentiation_from_prior_art="d",
        limitations="l",
    )


def test_unknown_route_returns_404() -> None:
    mod = _load()
    result = mod.handler({"routeKey": "DELETE /bad"}, None)
    assert result["statusCode"] == 404
    body = json.loads(result["body"])
    assert "Unknown route" in body["error"]


def test_missing_job_id_returns_400() -> None:
    mod = _load()
    result = mod.handler(_event("GET /api/jobs/{jobId}"), None)
    assert result["statusCode"] == 400
    assert json.loads(result["body"])["error"] == "jobId is required"


def test_unknown_job_returns_byok_failed_shape() -> None:
    fake_boto3 = MagicMock()
    fake_boto3.resource.return_value.Table.return_value.get_item.return_value = {"Item": None}
    with patch.dict(sys.modules, {"boto3": fake_boto3}):
        mod = _load()
        result = mod.handler(_event("GET /api/jobs/{jobId}", "no-such-job"), None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["status"] == "failed"
    assert body["result"] is None
    assert "Unknown job_id=no-such-job" in body["error"]


def test_completed_job_inlines_s3_result() -> None:
    payload = {"needs": [], "proposals": [], "status": "done", "reason": None}
    fake_s3_body = MagicMock(read=lambda: json.dumps(payload).encode())

    fake_boto3 = MagicMock()
    fake_boto3.resource.return_value.Table.return_value.get_item.return_value = {
        "Item": {
            "job_id": "j1",
            "status": "completed",
            "result_key": "results/j1.json",
        }
    }
    fake_boto3.client.return_value.get_object.return_value = {"Body": fake_s3_body}

    with patch.dict(sys.modules, {"boto3": fake_boto3}):
        mod = _load()
        result = mod.handler(_event("GET /api/jobs/{jobId}", "j1"), None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["status"] == "completed"
    assert body["result"] == payload


def test_runs_latest_empty() -> None:
    fake_store = MagicMock()
    fake_store.get_latest_gap_run = AsyncMock(return_value=None)

    with patch("whitespace.store.dynamo_store.DynamoSessionStore", return_value=fake_store):
        mod = _load()
        result = mod.handler(_event("GET /api/runs/latest"), None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["gap_run"] is None
    assert body["idea_runs"] == []


def test_runs_latest_populated() -> None:
    gap_run = GapRun(
        run_id="r1",
        timestamp=datetime.now(UTC),
        needs=[_need("Gap A")],
        domain="robotics",
    )
    idea_run = IdeaRun(
        run_id="ir1",
        gap_run_id="r1",
        timestamp=datetime.now(UTC),
        proposals=[_proposal("Idea X")],
        selected_need_titles=["Gap A"],
    )

    fake_store = MagicMock()
    fake_store.get_latest_gap_run = AsyncMock(return_value=gap_run)
    fake_store.list_idea_runs = AsyncMock(return_value=[idea_run])

    with patch("whitespace.store.dynamo_store.DynamoSessionStore", return_value=fake_store):
        mod = _load()
        result = mod.handler(_event("GET /api/runs/latest"), None)

    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["gap_run"]["run_id"] == "r1"
    assert body["gap_run"]["needs"][0]["title"] == "Gap A"
    assert len(body["idea_runs"]) == 1
    assert body["idea_runs"][0]["run_id"] == "ir1"
    assert body["idea_runs"][0]["proposals"][0]["title"] == "Idea X"
