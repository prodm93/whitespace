"""SaaS pipeline action tests: ideation, gap analysis, result computation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from _saas_helpers import FakePipeline, FakeStore, _need, _profile


@pytest.fixture(autouse=True)
def patch_actions(monkeypatch: Any) -> None:
    import _actions

    monkeypatch.setattr(_actions, "_pipeline", FakePipeline())
    monkeypatch.setattr(_actions, "_session_store", FakeStore())
    monkeypatch.setattr(_actions, "_ensure_init", AsyncMock())
    monkeypatch.setattr(_actions, "_localise_paths", AsyncMock(side_effect=lambda p: p))


@pytest.fixture()
def pipeline() -> FakePipeline:
    import _actions

    return _actions._pipeline  # type: ignore[attr-defined]


# --- _ideation_action ---


async def test_ideation_no_sidecar_is_guardrail_not_block() -> None:
    from _actions import _ideation_action

    session = {
        "profile": _profile().model_dump(),
        "needs": [_need("Gap A").model_dump()],
        "user_selected_titles": [],
        "gap_run_id": "",
    }
    r = await _ideation_action("j1", session, {"selected_titles": ["Gap A"]}, False)
    assert r["session_updates"].get("blocked_reason") is None
    assert "sidecar" in r["summary"]


async def test_ideation_wrong_titles_is_guardrail_not_block() -> None:
    from _actions import _ideation_action

    session = {
        "profile": _profile().model_dump(),
        "needs": [_need("Gap A").model_dump()],
        "user_selected_titles": ["Gap B"],
        "gap_run_id": "",
    }
    r = await _ideation_action("j1", session, {"selected_titles": ["Gap A"]}, False)
    assert r["session_updates"].get("blocked_reason") is None
    assert "confirmed" in r["summary"]


async def test_ideation_no_needs_sets_blocked_reason() -> None:
    from _actions import _ideation_action

    session = {
        "profile": _profile().model_dump(),
        "needs": [],
        "user_selected_titles": ["Gap A"],
        "gap_run_id": "",
    }
    r = await _ideation_action("j1", session, {"selected_titles": ["Gap A"]}, False)
    assert r["session_updates"].get("blocked_reason") is not None


async def test_ideation_no_profile_sets_blocked_reason() -> None:
    from _actions import _ideation_action

    session = {
        "profile": None,
        "needs": [_need("Gap A").model_dump()],
        "user_selected_titles": ["Gap A"],
        "gap_run_id": "",
    }
    r = await _ideation_action("j1", session, {"selected_titles": ["Gap A"]}, False)
    assert r["session_updates"].get("blocked_reason") is not None


async def test_ideation_valid_sidecar_calls_pipeline(
    pipeline: FakePipeline,
) -> None:
    from _actions import _ideation_action

    session = {
        "profile": _profile().model_dump(),
        "needs": [_need("Gap A").model_dump()],
        "user_selected_titles": ["Gap A"],
        "gap_run_id": "r1",
    }
    r = await _ideation_action("j1", session, {"selected_titles": ["Gap A"]}, False)
    assert pipeline.ideate_calls == 1
    assert r["session_updates"].get("blocked_reason") is None
    assert r["session_updates"].get("proposals")


# --- _gap_analysis_action ---


async def test_gap_analysis_no_profile_sets_blocked() -> None:
    from _actions import _gap_analysis_action

    r = await _gap_analysis_action(
        "j1",
        {"profile": None, "domain": "AI", "doc_paths": [], "keep_findings": False},
        False,
    )
    assert r["session_updates"].get("blocked_reason") is not None


async def test_gap_analysis_no_domain_sets_blocked() -> None:
    from _actions import _gap_analysis_action

    r = await _gap_analysis_action(
        "j1",
        {
            "profile": _profile().model_dump(),
            "domain": "",
            "doc_paths": [],
            "keep_findings": False,
        },
        False,
    )
    assert r["session_updates"].get("blocked_reason") is not None


async def test_gap_analysis_success(pipeline: FakePipeline) -> None:
    from _actions import _gap_analysis_action

    r = await _gap_analysis_action(
        "j1",
        {
            "profile": _profile().model_dump(),
            "domain": "AI",
            "doc_paths": [],
            "keep_findings": False,
        },
        False,
    )
    assert pipeline.analyse_calls == 1
    assert r["session_updates"].get("needs")
    assert r["session_updates"].get("blocked_reason") is None


# --- _compute_final_result ---


def test_final_result_done_when_proposals() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result({"proposals": [{"title": "x"}], "needs": [], "blocked_reason": None})
    assert r["status"] == "done"


def test_final_result_blocked_beats_awaiting() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result(
        {
            "proposals": [],
            "needs": [{"title": "x"}],
            "blocked_reason": "need profile",
        }
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
