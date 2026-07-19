"""Phase 2 SaaS orchestrator tests.

Tests the action-step logic directly (without the durable SDK) and
the end-to-end two-request flow through a FakeDurableContext. The
aws_durable_execution_sdk is stubbed at import time; the handler
directory is added to sys.path so handler.py and its siblings are
importable.

Coverage:
- Replay-safety: wait_for_callback is never called.
- Two-request flow: request 1 ends awaiting_selection with results in
  the store; request 2 rehydrates and ideates without re-running the
  council.
- Result contract parity with BYOK: {needs, proposals, status, reason}.
- Usage: blocked/query-only orchestrate does not call analyse_gaps.
- HITL invariants preserved in _ideation_action (no sidecar, wrong
  titles, no-needs all produce the correct outcomes per F1/F4).
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub the durable execution SDK before importing handler.py
# ---------------------------------------------------------------------------

_sdk = types.ModuleType("aws_durable_execution_sdk")


@dataclass
class FakeDurableContext:
    """Records step calls; raises on wait_for_callback (Phase 2 invariant)."""

    _journal: dict[str, Any] = field(default_factory=dict)
    step_calls: list[str] = field(default_factory=list)

    def step(self, fn: Any, *, name: str) -> Any:
        self.step_calls.append(name)
        if name in self._journal:
            return self._journal[name]
        result = fn()
        self._journal[name] = result
        return result

    def wait_for_callback(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("wait_for_callback must not be called in Phase 2 per 2a")


_sdk.DurableContext = FakeDurableContext
_sdk.durable_execution = lambda fn: fn  # no-op decorator for tests
sys.modules["aws_durable_execution_sdk"] = _sdk

_HANDLER_DIR = str(
    Path(__file__).parent.parent / "deploy" / "aws" / "lambda" / "pipeline_orchestrator"
)
if _HANDLER_DIR not in sys.path:
    sys.path.insert(0, _HANDLER_DIR)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

from whitespace.schemas.gap import UnmetNeed  # noqa: E402
from whitespace.schemas.idea import IdeationProposal  # noqa: E402
from whitespace.schemas.profile import ProfessionalProfile  # noqa: E402
from whitespace.store.base import GapRun  # noqa: E402


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


def _profile() -> ProfessionalProfile:
    return ProfessionalProfile(hard_skills=["Python"], domain_knowledge=["patents"])


class FakePipeline:
    def __init__(
        self,
        needs: list[UnmetNeed] | None = None,
        proposals: list[IdeationProposal] | None = None,
    ) -> None:
        self.needs = needs or [_need("Gap A")]
        self.proposals = proposals or [_proposal("Idea X")]
        self.analyse_calls = 0
        self.ideate_calls = 0
        self.router = FakeRouter([])

    async def extract_profile(self, _paths: list[str]) -> ProfessionalProfile:
        return _profile()

    async def analyse_gaps(self, *_a: Any, **_kw: Any) -> list[UnmetNeed]:
        self.analyse_calls += 1
        return self.needs

    async def ideate(self, *_a: Any, **_kw: Any) -> list[IdeationProposal]:
        self.ideate_calls += 1
        return self.proposals

    async def query(self, question: str) -> str:
        return f"answer: {question}"


class FakeRouter:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._resp = responses
        self._i = 0

    async def call(self, **_kw: Any) -> dict[str, Any]:
        if not self._resp:
            return {"content": "done", "tool_calls": [], "stop_reason": "end"}
        r = self._resp[min(self._i, len(self._resp) - 1)]
        self._i += 1
        return r


class FakeStore:
    def __init__(self, gap_run: GapRun | None = None) -> None:
        self._gap_run = gap_run

    async def get_latest_gap_run(self) -> GapRun | None:
        return self._gap_run


def _tc(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "content": "",
        "tool_calls": [{"id": "t0", "name": name, "arguments": args or {}}],
        "stop_reason": "tool_use",
    }


_DONE: dict[str, Any] = {"content": "ok", "tool_calls": [], "stop_reason": "end"}

# ---------------------------------------------------------------------------
# Fixtures: inject fake pipeline + store into _actions module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_actions(monkeypatch: Any) -> None:
    import _actions

    fake_pipeline = FakePipeline()
    monkeypatch.setattr(_actions, "_pipeline", fake_pipeline)
    monkeypatch.setattr(_actions, "_session_store", FakeStore())
    monkeypatch.setattr(_actions, "_ensure_init", AsyncMock())
    monkeypatch.setattr(_actions, "_localise_paths", AsyncMock(side_effect=lambda p: p))


@pytest.fixture()
def pipeline() -> FakePipeline:
    import _actions

    return _actions._pipeline  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _ideation_action: HITL invariants
# ---------------------------------------------------------------------------


async def test_ideation_no_sidecar_is_guardrail_not_block() -> None:
    from _actions import _ideation_action

    session = {
        "profile": _profile().model_dump(),
        "needs": [_need("Gap A").model_dump()],
        "user_selected_titles": [],
        "gap_run_id": "",
    }
    result = await _ideation_action("job1", session, {"selected_titles": ["Gap A"]}, False)

    assert "session_updates" in result
    assert result["session_updates"].get("blocked_reason") is None
    assert "sidecar" in result["summary"]


async def test_ideation_wrong_titles_is_guardrail_not_block() -> None:
    from _actions import _ideation_action

    session = {
        "profile": _profile().model_dump(),
        "needs": [_need("Gap A").model_dump()],
        "user_selected_titles": ["Gap B"],
        "gap_run_id": "",
    }
    result = await _ideation_action("job1", session, {"selected_titles": ["Gap A"]}, False)

    assert result["session_updates"].get("blocked_reason") is None
    assert "confirmed" in result["summary"]


async def test_ideation_no_needs_sets_blocked_reason() -> None:
    from _actions import _ideation_action

    session = {
        "profile": _profile().model_dump(),
        "needs": [],
        "user_selected_titles": ["Gap A"],
        "gap_run_id": "",
    }
    result = await _ideation_action("job1", session, {"selected_titles": ["Gap A"]}, False)

    assert result["session_updates"].get("blocked_reason") is not None


async def test_ideation_no_profile_sets_blocked_reason() -> None:
    from _actions import _ideation_action

    session = {
        "profile": None,
        "needs": [_need("Gap A").model_dump()],
        "user_selected_titles": ["Gap A"],
        "gap_run_id": "",
    }
    result = await _ideation_action("job1", session, {"selected_titles": ["Gap A"]}, False)

    assert result["session_updates"].get("blocked_reason") is not None


async def test_ideation_valid_sidecar_calls_pipeline(pipeline: FakePipeline) -> None:
    from _actions import _ideation_action

    session = {
        "profile": _profile().model_dump(),
        "needs": [_need("Gap A").model_dump()],
        "user_selected_titles": ["Gap A"],
        "gap_run_id": "run1",
    }
    result = await _ideation_action("job1", session, {"selected_titles": ["Gap A"]}, False)

    assert pipeline.ideate_calls == 1
    assert result["session_updates"].get("blocked_reason") is None
    assert result["session_updates"].get("proposals")


# ---------------------------------------------------------------------------
# _gap_analysis_action: prerequisite guards
# ---------------------------------------------------------------------------


async def test_gap_analysis_no_profile_sets_blocked() -> None:
    from _actions import _gap_analysis_action

    result = await _gap_analysis_action(
        "job1", {"profile": None, "domain": "AI", "doc_paths": [], "keep_findings": False}, False
    )
    assert result["session_updates"].get("blocked_reason") is not None


async def test_gap_analysis_no_domain_sets_blocked() -> None:
    from _actions import _gap_analysis_action

    result = await _gap_analysis_action(
        "job1",
        {"profile": _profile().model_dump(), "domain": "", "doc_paths": [], "keep_findings": False},
        False,
    )
    assert result["session_updates"].get("blocked_reason") is not None


async def test_gap_analysis_success(pipeline: FakePipeline) -> None:
    from _actions import _gap_analysis_action

    result = await _gap_analysis_action(
        "job1",
        {
            "profile": _profile().model_dump(),
            "domain": "AI sensors",
            "doc_paths": [],
            "keep_findings": False,
        },
        False,
    )
    assert pipeline.analyse_calls == 1
    assert result["session_updates"].get("needs")
    assert result["session_updates"].get("blocked_reason") is None


# ---------------------------------------------------------------------------
# _compute_final_result: status mapping
# ---------------------------------------------------------------------------


def test_final_result_done_when_proposals() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result({"proposals": [{"title": "x"}], "needs": [], "blocked_reason": None})
    assert r["status"] == "done"


def test_final_result_blocked_beats_awaiting() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result(
        {"proposals": [], "needs": [{"title": "x"}], "blocked_reason": "need profile"}
    )
    assert r["status"] == "blocked"
    assert r["reason"] == "need profile"


def test_final_result_awaiting_when_needs_no_proposals() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result({"proposals": [], "needs": [{"title": "x"}], "blocked_reason": None})
    assert r["status"] == "awaiting_selection"


def test_final_result_done_when_nothing() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result({"proposals": [], "needs": [], "blocked_reason": None})
    assert r["status"] == "done"


# ---------------------------------------------------------------------------
# End-to-end handler: two-request flow + no wait_for_callback
# ---------------------------------------------------------------------------


def test_wait_for_callback_never_called(monkeypatch: Any, pipeline: FakePipeline) -> None:
    """The durable function must not call wait_for_callback in Phase 2."""
    import _actions
    import handler

    pipeline.router = FakeRouter(
        [
            _tc("get_status"),
            _tc("extract_profile"),
            _tc("stage", {"domain": "robotics"}),
            _tc("run_gap_analysis"),
            _DONE,
        ]
    )
    monkeypatch.setattr(_actions, "_pipeline", pipeline)
    # boto3 calls inside _set_status/_publish would fail; mock them
    monkeypatch.setattr(handler, "JOBS_TABLE", "")
    monkeypatch.setattr(handler, "RESULTS_BUCKET", "")

    fake_boto3 = MagicMock()
    fake_boto3.resource.return_value.Table.return_value.put_item = MagicMock()
    fake_boto3.client.return_value.put_object = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    ctx = FakeDurableContext()
    event = {
        "job_id": "job1",
        "payload": {
            "intent": "Run gap analysis",
            "profile_paths": ["cv.pdf"],
            "doc_paths": [],
            "fresh_start": False,
            "selected_titles": [],
        },
    }
    result = handler.handler(event, ctx)

    assert "wait_for_callback" not in ctx.step_calls
    assert result["status"] == "awaiting_selection"
    assert result["needs"]


def test_request2_rehydrates_needs_without_rerunning_council(
    monkeypatch: Any, pipeline: FakePipeline
) -> None:
    """Request 2 (ideation) reads needs from the store, not from the council."""
    import _actions
    import handler

    prior_run = GapRun(
        run_id="run1",
        timestamp=datetime.now(UTC),
        needs=[_need("Gap A")],
        domain="robotics",
    )
    monkeypatch.setattr(_actions, "_session_store", FakeStore(gap_run=prior_run))
    monkeypatch.setattr(_actions, "_pipeline", pipeline)

    pipeline.router = FakeRouter(
        [
            _tc("get_status"),
            _tc("extract_profile"),
            _tc("run_ideation", {"selected_titles": ["Gap A"]}),
            _DONE,
        ]
    )

    fake_boto3 = MagicMock()
    fake_boto3.resource.return_value.Table.return_value.put_item = MagicMock()
    fake_boto3.client.return_value.put_object = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    ctx = FakeDurableContext()
    event = {
        "job_id": "job2",
        "payload": {
            "intent": "Run ideation on my selected gaps.",
            "selected_titles": ["Gap A"],
            "profile_paths": ["cv.pdf"],
            "doc_paths": [],
            "fresh_start": False,
        },
    }
    result = handler.handler(event, ctx)

    assert pipeline.analyse_calls == 0, "council must not re-run on request 2"
    assert pipeline.ideate_calls == 1
    assert result["status"] == "done"
    assert result["proposals"]
