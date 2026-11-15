"""SaaS pipeline action tests: ideation, gap analysis, result computation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from _saas_helpers import FakePipeline, FakeStore, _need, _profile, install_runtime


@pytest.fixture(autouse=True)
async def patch_actions(monkeypatch: Any, request: Any) -> FakePipeline:
    import _actions
    import _runtime

    fake = FakePipeline()
    install_runtime(monkeypatch, fake, FakeStore(), request)
    monkeypatch.setattr(
        _actions, "localise_paths", AsyncMock(side_effect=lambda paths, _owner: paths)
    )
    await _runtime.open_run("u1")
    return fake


@pytest.fixture()
def pipeline(patch_actions: FakePipeline) -> FakePipeline:
    return patch_actions


# --- _ideation_action ---


@pytest.mark.protects("gap-selection-user-only")
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


@pytest.mark.protects("gap-selection-user-only")
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


@pytest.mark.protects("missing-input-blocks-with-reason")
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


@pytest.mark.protects("missing-input-blocks-with-reason")
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


@pytest.mark.protects("missing-input-blocks-with-reason")
async def test_gap_analysis_no_profile_sets_blocked() -> None:
    from _actions import _gap_analysis_action

    r = await _gap_analysis_action(
        "j1",
        {"profile": None, "domain": "AI", "doc_paths": [], "keep_findings": False},
        False,
    )
    assert r["session_updates"].get("blocked_reason") is not None


@pytest.mark.protects("missing-input-blocks-with-reason")
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


async def test_extract_profile_downloads_as_the_tenant_of_the_open_run() -> None:
    import _actions
    from _actions import _extract_profile_action

    await _extract_profile_action({"profile_paths": ["uploads/u1/cv.pdf"]})

    _actions.localise_paths.assert_awaited_once_with(["uploads/u1/cv.pdf"], "u1")  # type: ignore[attr-defined]


async def test_gap_analysis_downloads_as_the_tenant_of_the_open_run() -> None:
    import _actions
    from _actions import _gap_analysis_action

    await _gap_analysis_action(
        "j1",
        {
            "profile": _profile().model_dump(),
            "domain": "AI",
            "doc_paths": ["uploads/u1/paper.pdf"],
            "keep_findings": False,
        },
        False,
    )

    _actions.localise_paths.assert_awaited_once_with(["uploads/u1/paper.pdf"], "u1")  # type: ignore[attr-defined]
