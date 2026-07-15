"""Phase 1 orchestration tests.

Covers: HITL sidecar invariants, blocked-reason semantics, status
mapping, two-request flow, write-through, AppState reset, and 404s
for deleted trigger routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from whitespace.agents._orchestrator_actions import OrchestratorActions
from whitespace.agents._orchestrator_session import AnalysisSession
from whitespace.agents.orchestrator_agent import OrchestratorAgent
from whitespace.api.state import AppState
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile

# ---------------------------------------------------------------------------
# Fake test doubles
# ---------------------------------------------------------------------------


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


@dataclass
class FakeWriter:
    profile: ProfessionalProfile | None = None
    domain: str = ""
    doc_paths: list[str] = field(default_factory=list)
    keep_findings: bool = False

    def set_profile(self, p: ProfessionalProfile) -> None:
        self.profile = p

    def set_pending_ingest(self, domain: str, paths: list[str], keep: bool) -> None:
        self.domain = domain
        self.doc_paths = paths
        self.keep_findings = keep


class FakePipeline:
    def __init__(
        self,
        needs: list[UnmetNeed] | None = None,
        proposals: list[IdeationProposal] | None = None,
    ) -> None:
        self.needs = needs if needs is not None else [_need("Gap A")]
        self.proposals = proposals if proposals is not None else [_proposal("Idea X")]
        self.analyse_calls = 0
        self.ideate_calls = 0
        self.closed = False

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

    async def close(self) -> None:
        self.closed = True


class FakeRouter:
    """Feeds scripted responses to the tool loop."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._resp = responses
        self._i = 0

    async def call(self, **_kw: Any) -> dict[str, Any]:
        r = self._resp[min(self._i, len(self._resp) - 1)]
        self._i += 1
        return r


def _tc(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "content": "",
        "tool_calls": [{"id": "t0", "name": name, "arguments": args or {}}],
        "stop_reason": "tool_use",
    }


_DONE: dict[str, Any] = {"content": "ok", "tool_calls": [], "stop_reason": "end"}


# ---------------------------------------------------------------------------
# OrchestratorActions: HITL invariants
# ---------------------------------------------------------------------------


async def test_gap_analysis_runs_only_once_per_job() -> None:
    pipeline = FakePipeline()
    session = AnalysisSession(profile=_profile(), domain="AI", profile_paths=["cv.pdf"])
    actions = OrchestratorActions(pipeline, session)  # type: ignore[arg-type]

    await actions.dispatch("run_gap_analysis", {})
    result = await actions.dispatch("run_gap_analysis", {})

    assert pipeline.analyse_calls == 1
    assert "already ran" in result


async def test_ideation_no_sidecar_is_guardrail_not_block() -> None:
    pipeline = FakePipeline()
    session = AnalysisSession(profile=_profile(), needs=[_need("Gap A")])
    actions = OrchestratorActions(pipeline, session)  # type: ignore[arg-type]

    await actions.dispatch("run_ideation", {"selected_titles": ["Gap A"]})

    assert pipeline.ideate_calls == 0
    assert session.blocked_reason is None


async def test_ideation_wrong_titles_is_guardrail_not_block() -> None:
    pipeline = FakePipeline()
    session = AnalysisSession(
        profile=_profile(),
        needs=[_need("Gap A")],
        user_selected_titles=["Gap B"],
    )
    actions = OrchestratorActions(pipeline, session)  # type: ignore[arg-type]

    await actions.dispatch("run_ideation", {"selected_titles": ["Gap A"]})

    assert pipeline.ideate_calls == 0
    assert session.blocked_reason is None


async def test_ideation_no_needs_sets_blocked_reason() -> None:
    pipeline = FakePipeline()
    session = AnalysisSession(profile=_profile(), user_selected_titles=["Gap A"])
    actions = OrchestratorActions(pipeline, session)  # type: ignore[arg-type]

    await actions.dispatch("run_ideation", {"selected_titles": ["Gap A"]})

    assert session.blocked_reason is not None
    assert pipeline.ideate_calls == 0


async def test_extract_profile_no_paths_sets_blocked_reason() -> None:
    session = AnalysisSession()
    actions = OrchestratorActions(FakePipeline(), session)  # type: ignore[arg-type]

    await actions.dispatch("extract_profile", {})

    assert session.blocked_reason is not None


# ---------------------------------------------------------------------------
# OrchestratorActions: successful operations clear blocked_reason
# ---------------------------------------------------------------------------


async def test_stage_clears_blocked_reason() -> None:
    session = AnalysisSession(blocked_reason="stale")
    actions = OrchestratorActions(FakePipeline(), session)  # type: ignore[arg-type]

    await actions.dispatch("stage", {"domain": "robotics"})

    assert session.blocked_reason is None


async def test_extract_profile_clears_blocked_reason() -> None:
    session = AnalysisSession(profile_paths=["cv.pdf"], blocked_reason="stale")
    actions = OrchestratorActions(FakePipeline(), session)  # type: ignore[arg-type]

    await actions.dispatch("extract_profile", {})

    assert session.blocked_reason is None


async def test_gap_analysis_clears_blocked_reason() -> None:
    session = AnalysisSession(profile=_profile(), domain="AI", blocked_reason="stale")
    actions = OrchestratorActions(FakePipeline(), session)  # type: ignore[arg-type]

    await actions.dispatch("run_gap_analysis", {})

    assert session.blocked_reason is None


async def test_ideation_clears_blocked_reason() -> None:
    session = AnalysisSession(
        profile=_profile(),
        needs=[_need("Gap A")],
        user_selected_titles=["Gap A"],
        blocked_reason="stale",
    )
    actions = OrchestratorActions(FakePipeline(), session)  # type: ignore[arg-type]

    await actions.dispatch("run_ideation", {"selected_titles": ["Gap A"]})

    assert session.blocked_reason is None


# ---------------------------------------------------------------------------
# OrchestratorActions: write-through to state writer
# ---------------------------------------------------------------------------


async def test_extract_profile_writes_through() -> None:
    sw = FakeWriter()
    session = AnalysisSession(profile_paths=["cv.pdf"])
    actions = OrchestratorActions(FakePipeline(), session, state_writer=sw)  # type: ignore[arg-type]

    await actions.dispatch("extract_profile", {})

    assert sw.profile is not None


async def test_stage_writes_through() -> None:
    sw = FakeWriter()
    session = AnalysisSession()
    actions = OrchestratorActions(FakePipeline(), session, state_writer=sw)  # type: ignore[arg-type]

    await actions.dispatch("stage", {"domain": "quantum", "keep_findings": True})

    assert sw.domain == "quantum"
    assert sw.keep_findings is True


# ---------------------------------------------------------------------------
# Status mapping (OrchestratorAgent with a script that terminates immediately)
# ---------------------------------------------------------------------------


async def test_status_proposals_is_done() -> None:
    session = AnalysisSession(proposals=[_proposal("X")])
    result = await OrchestratorAgent(FakeRouter([_DONE])).run(  # type: ignore[arg-type]
        "i",
        OrchestratorActions(FakePipeline(), session),  # type: ignore[arg-type]
    )
    assert result.status == "done"


async def test_status_blocked_wins_over_awaiting_selection() -> None:
    session = AnalysisSession(needs=[_need("A")], blocked_reason="missing profile")
    result = await OrchestratorAgent(FakeRouter([_DONE])).run(  # type: ignore[arg-type]
        "i",
        OrchestratorActions(FakePipeline(), session),  # type: ignore[arg-type]
    )
    assert result.status == "blocked"
    assert result.reason == "missing profile"


async def test_status_needs_is_awaiting_selection() -> None:
    session = AnalysisSession(needs=[_need("A")])
    result = await OrchestratorAgent(FakeRouter([_DONE])).run(  # type: ignore[arg-type]
        "i",
        OrchestratorActions(FakePipeline(), session),  # type: ignore[arg-type]
    )
    assert result.status == "awaiting_selection"


async def test_status_all_empty_is_done() -> None:
    session = AnalysisSession()
    result = await OrchestratorAgent(FakeRouter([_DONE])).run(  # type: ignore[arg-type]
        "i",
        OrchestratorActions(FakePipeline(), session),  # type: ignore[arg-type]
    )
    assert result.status == "done"


# ---------------------------------------------------------------------------
# End-to-end two-request flow
# ---------------------------------------------------------------------------


async def test_request1_produces_awaiting_selection() -> None:
    pipeline = FakePipeline(needs=[_need("Gap A"), _need("Gap B")])
    sw = FakeWriter()
    session = AnalysisSession(profile_paths=["cv.pdf"])
    actions = OrchestratorActions(pipeline, session, state_writer=sw)  # type: ignore[arg-type]

    result = await OrchestratorAgent(
        FakeRouter(
            [  # type: ignore[arg-type]
                _tc("stage", {"domain": "robotics"}),
                _tc("extract_profile"),
                _tc("run_gap_analysis"),
                _DONE,
            ]
        )
    ).run("stage robotics and run gap analysis", actions)

    assert result.status == "awaiting_selection"
    assert {n.title for n in result.needs} == {"Gap A", "Gap B"}
    assert sw.profile is not None


async def test_request2_sidecar_produces_done() -> None:
    pipeline = FakePipeline(proposals=[_proposal("Idea X")])
    session = AnalysisSession(
        profile=_profile(),
        needs=[_need("Gap A")],
        user_selected_titles=["Gap A"],
    )
    result = await OrchestratorAgent(
        FakeRouter(
            [  # type: ignore[arg-type]
                _tc("run_ideation", {"selected_titles": ["Gap A"]}),
                _DONE,
            ]
        )
    ).run("ideate on Gap A", OrchestratorActions(pipeline, session))  # type: ignore[arg-type]

    assert result.status == "done"
    assert pipeline.analyse_calls == 0
    assert pipeline.ideate_calls == 1


async def test_model_cannot_ideate_without_sidecar_in_request1() -> None:
    pipeline = FakePipeline()
    session = AnalysisSession(
        profile=_profile(),
        domain="AI",
        needs=[_need("Gap A")],
    )
    result = await OrchestratorAgent(
        FakeRouter(
            [  # type: ignore[arg-type]
                _tc("run_ideation", {"selected_titles": ["Gap A"]}),
                _DONE,
            ]
        )
    ).run("run everything", OrchestratorActions(pipeline, session))  # type: ignore[arg-type]

    assert result.status == "awaiting_selection"
    assert pipeline.ideate_calls == 0
    assert result.reason is None


# ---------------------------------------------------------------------------
# F2: Rehydrated needs enable request-2 ideation without re-running analysis
# ---------------------------------------------------------------------------


async def test_rehydrated_needs_enable_ideation_without_gap_rerun() -> None:
    pipeline = FakePipeline(proposals=[_proposal("Idea X")])
    session = AnalysisSession(
        profile=_profile(),
        needs=[_need("Gap A")],
        user_selected_titles=["Gap A"],
    )
    result = await OrchestratorAgent(
        FakeRouter(
            [  # type: ignore[arg-type]
                _tc("run_ideation", {"selected_titles": ["Gap A"]}),
                _DONE,
            ]
        )
    ).run("ideate", OrchestratorActions(pipeline, session))  # type: ignore[arg-type]

    assert result.status == "done"
    assert pipeline.analyse_calls == 0


# ---------------------------------------------------------------------------
# F4: No-gap-results ideation dead-end must surface as blocked
# ---------------------------------------------------------------------------


async def test_no_needs_anywhere_yields_blocked() -> None:
    pipeline = FakePipeline()
    session = AnalysisSession(profile=_profile(), user_selected_titles=["Gap A"])
    result = await OrchestratorAgent(
        FakeRouter(
            [  # type: ignore[arg-type]
                _tc("run_ideation", {"selected_titles": ["Gap A"]}),
                _DONE,
            ]
        )
    ).run("ideate", OrchestratorActions(pipeline, session))  # type: ignore[arg-type]

    assert result.status == "blocked"
    assert result.reason is not None


# ---------------------------------------------------------------------------
# F5: AppState.reset() is pipeline-only
# ---------------------------------------------------------------------------


async def test_reset_preserves_profile_and_staging() -> None:
    state = AppState()
    state.set_profile(_profile())
    state.set_profile_paths(["cv.pdf"])
    state.set_pending_ingest("quantum", ["d.pdf"], True)

    await state.reset()

    assert state.get_profile().hard_skills == ["Python"]
    assert state.get_profile_paths() == ["cv.pdf"]
    domain, paths, keep = state.get_pending_ingest()
    assert domain == "quantum"
    assert paths == ["d.pdf"]
    assert keep is True


async def test_reset_closes_and_clears_pipeline() -> None:
    state = AppState()
    pipeline = FakePipeline()
    state._pipeline = pipeline  # type: ignore[attr-defined]

    await state.reset()

    assert pipeline.closed
    assert state._pipeline is None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Deleted trigger routes return 404; ingest still works
# ---------------------------------------------------------------------------


@pytest.fixture()
def app(tmp_path: Any) -> Any:
    from whitespace.api.app import create_app
    from whitespace.config import Config

    cfg = Config(sqlite_db_path=str(tmp_path / "ws.db"))
    return create_app(cfg)


async def test_deleted_routes_return_404(app: Any) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/api/gaps", "/api/ideate", "/api/query", "/api/profile"):
            resp = await client.post(path, json={})
            assert resp.status_code == 404, f"{path!r} must not exist"


async def test_ingest_route_still_works(app: Any) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/ingest", data={"domain": "test domain"})
        assert resp.status_code == 200
