"""BYOK starts a session with the profile stored with the gap run, and never with an older one."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from whitespace.api.handlers import _run_orchestrator, register_handlers
from whitespace.api.state import AppState
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.store.base import GapRun
from whitespace.store.sqlite_store import SqliteSessionStore

_NEED = UnmetNeed(title="Gap A", description="d", current_state="c", why_unmet="w")
_STORED = ProfessionalProfile(hard_skills=["stored skill"])
_PROPOSAL = IdeationProposal(
    title="Idea X",
    problem_statement="p",
    technical_approach="t",
    why_this_person="y",
    differentiation_from_prior_art="d",
    limitations="l",
)
_IDEATE = {
    "content": "",
    "tool_calls": [
        {"id": "t0", "name": "run_ideation", "arguments": {"selected_titles": ["Gap A"]}}
    ],
    "stop_reason": "tool_use",
}
_DONE = {"content": "ok", "tool_calls": [], "stop_reason": "end"}


class _Router:
    def __init__(self) -> None:
        self.replies = [_IDEATE, _DONE]

    async def call(self, **_kw: Any) -> dict[str, Any]:
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


class _Pipeline:
    def __init__(self) -> None:
        self.router = _Router()
        self.ideated_with: list[ProfessionalProfile] = []

    async def ideate_with_questions(
        self, _needs: Any, profile: ProfessionalProfile, **_kw: Any
    ) -> list[IdeationProposal]:
        self.ideated_with.append(profile)
        return [_PROPOSAL]

    async def pending_questions(self) -> None:
        return None


class _Queue:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def register_handler(self, name: str, handler: Any) -> None:
        self.handlers[name] = handler


async def _state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stored: ProfessionalProfile | None
) -> AppState:
    store = SqliteSessionStore(tmp_path / "ws.db")
    run = GapRun(run_id="r1", timestamp=datetime.now(UTC), needs=[_NEED], profile=stored)
    await store.save_gap_run(run)
    state = AppState()
    state.set_store(store)
    monkeypatch.setattr("whitespace.api.state.app_state", state)
    return state


async def _ideate(pipeline: _Pipeline) -> dict[str, Any]:
    payload = {"intent": "Ideate on Gap A", "selected_titles": ["Gap A"]}
    return await _run_orchestrator("job-2", payload, pipeline)  # type: ignore[arg-type]


@pytest.mark.protects("byok-ideation-after-a-restart")
async def test_after_a_restart_the_session_starts_with_the_stored_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    await _state(monkeypatch, tmp_path, _STORED)
    pipeline = _Pipeline()

    result = await _ideate(pipeline)

    assert result["status"] == "done"
    assert pipeline.ideated_with == [_STORED]


@pytest.mark.protects("new-profile-documents-never-use-an-older-profile")
async def test_staged_profile_documents_keep_the_stored_profile_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = await _state(monkeypatch, tmp_path, _STORED)
    state.set_profile_paths(["uploads/new-cv.pdf"])
    pipeline = _Pipeline()

    result = await _ideate(pipeline)

    assert pipeline.ideated_with == []
    assert result["reason"] == "Cannot run: no profile."


@pytest.mark.protects("new-profile-documents-never-use-an-older-profile")
async def test_an_ingest_of_profile_documents_drops_the_held_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = await _state(monkeypatch, tmp_path, None)
    state.set_profile(ProfessionalProfile(hard_skills=["held skill"]))
    queue = _Queue()
    register_handlers(queue)  # type: ignore[arg-type]
    pipeline = _Pipeline()

    await queue.handlers["ingest"]("job-1", {"profile_paths": ["uploads/new-cv.pdf"]})
    result = await _ideate(pipeline)

    assert pipeline.ideated_with == []
    assert result["reason"] == "Cannot run: no profile."
