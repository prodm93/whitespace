"""Tests for gap citation flow: finding keys, evidence parsing, pool formatting."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from whitespace.agents.council._helpers import format_for_synthesis, format_pool
from whitespace.agents.council._revision import request_revisions
from whitespace.orchestration._research_stage import format_findings
from whitespace.orchestration._trail_rendering import build_exploration_context
from whitespace.schemas.critique import CriticAssessment, CriticReport
from whitespace.schemas.gap import CandidateGap
from whitespace.schemas.research import RawFinding

_TS = datetime(2026, 7, 1, tzinfo=UTC)


def _finding(title: str = "Finding") -> RawFinding:
    return RawFinding(
        title=title,
        content="content text",
        source_type="paper",
        source_name="src",
        query="query",
        found_at=_TS,
    )


def _gap(candidate_id: str = "role_a-1", evidence: list[str] | None = None) -> CandidateGap:
    return CandidateGap(
        title="Some gap",
        description="Description",
        source_model="model-a",
        candidate_id=candidate_id,
        evidence=evidence or [],
    )


def _report(cid: str) -> CriticReport:
    return CriticReport(
        assessments=[CriticAssessment(candidate_id=cid, verdict="keep")],
        ranking=[cid],
    )


# ---------------------------------------------------------------------------
# format_findings keys
# ---------------------------------------------------------------------------


class TestFormatFindingsKeys:
    def test_single_finding_has_f1_key(self) -> None:
        assert "[F1]" in format_findings([_finding()])

    def test_keys_are_sequential(self) -> None:
        text = format_findings([_finding(f"T{i}") for i in range(1, 4)])
        assert "[F1]" in text and "[F2]" in text and "[F3]" in text

    def test_key_appears_before_source_type(self) -> None:
        text = format_findings([_finding()])
        assert text.index("[F1]") < text.index("[paper]")

    def test_keys_stable_for_same_input(self) -> None:
        f = _finding()
        assert format_findings([f]) == format_findings([f])

    def test_empty_findings_returns_placeholder(self) -> None:
        assert format_findings([]) == "(no research findings)"


# ---------------------------------------------------------------------------
# Evidence parsing (simulates gap_identifier.run / revise logic)
# ---------------------------------------------------------------------------


class TestEvidenceParsing:
    def test_evidence_list_round_trips(self) -> None:
        raw = json.dumps(
            {"gaps": [{"title": "T", "description": "D", "evidence": ["[F3]", "graph: path"]}]}
        )
        g = json.loads(raw)["gaps"][0]
        gap = CandidateGap(
            title=g["title"],
            description=g["description"],
            source_model="m",
            evidence=[e for e in g.get("evidence", []) if isinstance(e, str)],
        )
        assert gap.evidence == ["[F3]", "graph: path"]

    def test_absent_evidence_yields_empty_list(self) -> None:
        raw = json.dumps({"gaps": [{"title": "T", "description": "D"}]})
        g = json.loads(raw)["gaps"][0]
        evidence = [e for e in g.get("evidence", []) if isinstance(e, str)]
        assert evidence == []

    def test_non_string_evidence_items_filtered(self) -> None:
        items = [{"title": "T", "description": "D", "evidence": ["[F1]", 42, None, "graph: x"]}]
        raw = json.dumps({"gaps": items})
        g = json.loads(raw)["gaps"][0]
        evidence = [e for e in g.get("evidence", []) if isinstance(e, str)]
        assert evidence == ["[F1]", "graph: x"]

    def test_revision_evidence_preserved(self) -> None:
        raw = json.dumps({"gaps": [{"title": "R", "description": "Revised", "evidence": ["[F5]"]}]})
        item = json.loads(raw)["gaps"][0]
        evidence = [e for e in item.get("evidence", []) if isinstance(e, str)]
        assert evidence == ["[F5]"]


# ---------------------------------------------------------------------------
# format_pool evidence rendering
# ---------------------------------------------------------------------------


class TestFormatPoolEvidence:
    def test_evidence_rendered_when_present(self) -> None:
        text = format_pool([_gap(evidence=["[F3]", "graph: ceramic path"])])
        assert "[F3]" in text
        assert "graph: ceramic path" in text

    def test_evidence_omitted_when_empty(self) -> None:
        assert "evidence:" not in format_pool([_gap(evidence=[])])

    def test_candidate_without_evidence_attr_renders_without_evidence_line(self) -> None:
        class _IdeaLike:
            candidate_id = "i-1"
            source_model = "m"
            title = "Idea"
            description = "Desc"

        text = format_pool([_IdeaLike()])  # type: ignore[arg-type]
        assert "evidence:" not in text


# ---------------------------------------------------------------------------
# format_for_synthesis evidence rendering
# ---------------------------------------------------------------------------


class TestFormatForSynthesisEvidence:
    def test_evidence_appears_in_synthesis_text(self) -> None:
        gap = _gap("role_a-1", evidence=["[F2]", "graph: battery path"])
        text = format_for_synthesis([gap], _report("role_a-1"))
        assert "[F2]" in text
        assert "graph: battery path" in text

    def test_no_evidence_line_when_empty(self) -> None:
        text = format_for_synthesis([_gap("role_a-1", evidence=[])], _report("role_a-1"))
        assert "evidence:" not in text


# ---------------------------------------------------------------------------
# build_exploration_context
# ---------------------------------------------------------------------------


class _MockScorer:
    async def score_against(self, texts: list[str], reference: list[str]) -> list[float]:
        return [0.0] * len(texts)


def _ctx(roles: set[str], findings_by_role: dict[str, str]) -> str:
    return asyncio.run(build_exploration_context(roles, findings_by_role, {}, _MockScorer()))


class TestBuildExplorationContext:
    def test_all_roles_in_output(self) -> None:
        ctx = _ctx({"role_a", "role_b"}, {"role_a": "exp_a", "role_b": "exp_b"})
        assert "role_a" in ctx and "role_b" in ctx

    def test_only_specified_roles_included(self) -> None:
        ctx = _ctx({"role_a"}, {"role_a": "exp_a", "role_b": "exp_b"})
        assert "role_a" in ctx
        assert "role_b" not in ctx

    def test_empty_when_no_findings_for_roles(self) -> None:
        assert _ctx({"role_a"}, {}) == ""

    def test_empty_exploration_strings_skipped(self) -> None:
        ctx = _ctx({"role_a", "role_b"}, {"role_a": "", "role_b": "content"})
        assert "role_a" not in ctx
        assert "role_b" in ctx

    def test_roles_sorted_alphabetically(self) -> None:
        ctx = _ctx({"role_b", "role_a"}, {"role_a": "a", "role_b": "b"})
        assert ctx.index("role_a") < ctx.index("role_b")

    def test_surviving_roles_differ_from_all_roles(self) -> None:
        all_ctx = _ctx({"role_a", "role_b"}, {"role_a": "a", "role_b": "b"})
        surviving_ctx = _ctx({"role_a"}, {"role_a": "a", "role_b": "b"})
        assert "role_b" in all_ctx
        assert "role_b" not in surviving_ctx


# ---------------------------------------------------------------------------
# A1: revision path evidence and findings grounding
# ---------------------------------------------------------------------------


def _mock_router(response_key: str = "gaps") -> MagicMock:
    router = MagicMock()
    router.call = AsyncMock(
        return_value={"model_id": "m", "content": json.dumps({response_key: []})}
    )
    return router


class TestRevisionEvidence:
    def test_evidence_line_present_in_revision_request(self) -> None:
        gap = _gap("r-1", evidence=["[F3]", "graph: ceramic path"])
        router = _mock_router()
        asyncio.run(
            request_revisions(
                router,
                role="role_a",
                system_prompt="sys",
                response_format={"type": "json_object"},
                response_key="gaps",
                flagged=[(gap, "sharpen this")],
                graph_context="graph exploration text",
                profile=MagicMock(),
            )
        )
        user_msg = router.call.call_args[1]["messages"][1]["content"]
        assert "evidence:" in user_msg
        assert "[F3]" in user_msg
        assert "graph: ceramic path" in user_msg

    def test_no_evidence_line_when_gap_has_none(self) -> None:
        gap = _gap("r-1", evidence=[])
        router = _mock_router()
        asyncio.run(
            request_revisions(
                router,
                role="role_a",
                system_prompt="sys",
                response_format={"type": "json_object"},
                response_key="gaps",
                flagged=[(gap, "sharpen this")],
                graph_context="ctx",
                profile=MagicMock(),
            )
        )
        user_msg = router.call.call_args[1]["messages"][1]["content"]
        assert "evidence:" not in user_msg

    def test_findings_text_in_revision_context(self) -> None:
        gap = _gap("r-1", evidence=["[F1]"])
        router = _mock_router()
        findings_text = "[F1] [paper] Some finding (2026-01-01): content"
        asyncio.run(
            request_revisions(
                router,
                role="role_a",
                system_prompt="sys",
                response_format={"type": "json_object"},
                response_key="gaps",
                flagged=[(gap, "feedback")],
                graph_context=findings_text + "\n\nexploration transcript",
                profile=MagicMock(),
            )
        )
        user_msg = router.call.call_args[1]["messages"][1]["content"]
        assert "[F1]" in user_msg
        assert "Some finding" in user_msg
