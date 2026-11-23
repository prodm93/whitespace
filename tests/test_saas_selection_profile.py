"""In SaaS, a request after the gap selection uses the profile stored with the gap run."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from _saas_helpers import (
    _DONE,
    FakeDurableContext,
    FakePipeline,
    FakeRouter,
    FakeStore,
    _evt,
    _need,
    _profile,
    _tc,
    install_runtime,
)

from whitespace.schemas.profile import ProfessionalProfile
from whitespace.store.base import GapRun

_STORED = ProfessionalProfile(hard_skills=["stored skill"], domain_knowledge=["robotics"])


class _RecordingPipeline(FakePipeline):
    def __init__(self) -> None:
        super().__init__()
        self.extract_calls = 0
        self.analysed_profiles: list[ProfessionalProfile] = []

    async def extract_profile(self, _paths: list[str]) -> ProfessionalProfile:
        self.extract_calls += 1
        return _profile()

    async def analyse_gaps(self, profile: ProfessionalProfile, *_a: Any, **_kw: Any) -> Any:
        self.analysed_profiles.append(profile)
        return await super().analyse_gaps()


def _run(monkeypatch: Any, request: Any, steps: list[dict[str, Any]], **event: Any) -> Any:
    import _actions
    import handler

    pipeline = _RecordingPipeline()
    pipeline.router = FakeRouter([*steps, _DONE])
    prior = GapRun(
        run_id="r1",
        timestamp=datetime.now(UTC),
        needs=[_need("Gap A")],
        domain="robotics",
        profile=event.pop("stored", _STORED),
    )
    install_runtime(monkeypatch, pipeline, FakeStore(gap_run=prior), request)
    monkeypatch.setattr(
        _actions, "localise_paths", AsyncMock(side_effect=lambda paths, _owner: paths)
    )
    monkeypatch.setitem(sys.modules, "boto3", MagicMock())
    monkeypatch.setattr(handler, "_validate_and_start", lambda _jid, _uid: "not_required")
    result = handler.handler(_evt("j2", "Go on", user_id="u1", **event), FakeDurableContext())
    return result, pipeline


@pytest.mark.protects("selection-ideates-without-a-new-upload")
def test_the_selection_alone_reaches_ideation_with_the_stored_profile(
    monkeypatch: Any, request: Any
) -> None:
    steps = [_tc("get_status"), _tc("run_ideation", {"selected_titles": ["Gap A"]})]

    result, pipeline = _run(monkeypatch, request, steps, selected_titles=["Gap A"])

    assert (pipeline.ideate_calls, pipeline.extract_calls) == (1, 0)
    assert result["status"] == "done"


def test_a_fresh_start_with_no_upload_analyses_with_the_stored_profile(
    monkeypatch: Any, request: Any
) -> None:
    steps = [_tc("get_status"), _tc("run_gap_analysis")]

    _, pipeline = _run(monkeypatch, request, steps, fresh_start=True)

    assert pipeline.analysed_profiles == [_STORED]


@pytest.mark.protects("new-profile-documents-never-use-an-older-profile")
def test_new_profile_documents_are_extracted_and_the_stored_profile_is_not_used(
    monkeypatch: Any, request: Any
) -> None:
    steps = [_tc("get_status"), _tc("extract_profile"), _tc("run_gap_analysis")]

    _, pipeline = _run(monkeypatch, request, steps, profile_paths=["uploads/u1/new-cv.pdf"])

    assert pipeline.analysed_profiles == [_profile()]


@pytest.mark.protects("new-profile-documents-never-use-an-older-profile")
def test_new_profile_documents_with_no_extraction_run_no_analysis(
    monkeypatch: Any, request: Any
) -> None:
    steps = [_tc("get_status"), _tc("run_gap_analysis")]

    result, pipeline = _run(monkeypatch, request, steps, profile_paths=["uploads/u1/new-cv.pdf"])

    assert pipeline.analysed_profiles == []
    assert result["status"] == "blocked"


def test_no_stored_profile_and_no_upload_is_blocked(monkeypatch: Any, request: Any) -> None:
    steps = [_tc("get_status"), _tc("run_ideation", {"selected_titles": ["Gap A"]})]

    result, pipeline = _run(monkeypatch, request, steps, selected_titles=["Gap A"], stored=None)

    assert pipeline.ideate_calls == 0
    assert result["status"] == "blocked"
    assert result["reason"] == "Cannot run: no profile."
