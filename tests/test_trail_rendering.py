"""Tests for A2: extractive trail rendering and per-channel budget caps."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from whitespace.orchestration._research_stage import _MAX_FINDINGS_CHARS, format_findings
from whitespace.orchestration._trail_rendering import (
    _MIN_TRAIL_CHUNKS,
    _TRAIL_BUDGET_CHARS,
    _assemble_indexed,
    _assemble_list,
    _parse_trail,
    _select_by_score,
    build_exploration_context,
    build_gap_references,
    render_trail,
)
from whitespace.schemas.gap import CandidateGap
from whitespace.schemas.research import RawFinding

_TS = datetime(2026, 7, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Scorer:
    """Mock scorer returning preset scores in order."""

    def __init__(self, scores: list[float]) -> None:
        self._scores = scores

    async def score_against(self, texts: list[str], reference: list[str]) -> list[float]:
        return self._scores[: len(texts)]


class _FailScorer:
    async def score_against(self, texts: list[str], reference: list[str]) -> list[float]:
        raise RuntimeError("embed failure")


class _ZeroScorer:
    async def score_against(self, texts: list[str], reference: list[str]) -> list[float]:
        return [0.0] * len(texts)


def _gap(title: str = "G", evidence: list[str] | None = None) -> CandidateGap:
    return CandidateGap(
        title=title,
        description="desc",
        source_model="m",
        evidence=evidence or [],
    )


def _finding(title: str = "F") -> RawFinding:
    return RawFinding(
        title=title,
        content="content",
        source_type="paper",
        source_name="src",
        query="q",
        found_at=_TS,
    )


def _tool_chunk(n: int) -> str:
    return f"### search_graph({{'q': 'q{n}'}})\nresult {n}"


def _transcript(*chunks: str, summary: str = "Closing summary.") -> str:
    return "\n\n".join([*chunks, summary])


# ---------------------------------------------------------------------------
# _parse_trail
# ---------------------------------------------------------------------------


class TestParseTrail:
    def test_tool_chunks_and_summary_separated(self) -> None:
        t = _transcript(_tool_chunk(1), _tool_chunk(2))
        chunks, summary = _parse_trail(t)
        assert len(chunks) == 2
        assert summary == "Closing summary."

    def test_no_tools_returns_empty_chunks(self) -> None:
        chunks, summary = _parse_trail("Just a plain summary.")
        assert chunks == []
        assert summary == "Just a plain summary."

    def test_placeholder_returns_empty_chunks(self) -> None:
        chunks, summary = _parse_trail("(no findings gathered)")
        assert chunks == []

    def test_no_closing_summary_when_cap_hit(self) -> None:
        transcript = "\n\n".join([_tool_chunk(1), _tool_chunk(2)])
        chunks, summary = _parse_trail(transcript)
        assert len(chunks) == 2
        assert summary == ""

    def test_chunk_order_preserved(self) -> None:
        t = _transcript(_tool_chunk(1), _tool_chunk(2), _tool_chunk(3))
        chunks, _ = _parse_trail(t)
        assert "q1" in chunks[0] and "q2" in chunks[1] and "q3" in chunks[2]


# ---------------------------------------------------------------------------
# build_gap_references
# ---------------------------------------------------------------------------


class TestBuildGapReferences:
    def test_title_description_entry_present(self) -> None:
        refs = build_gap_references([_gap("Gap title")])
        assert any("Gap title" in r for r in refs)

    def test_graph_citation_is_own_entry(self) -> None:
        refs = build_gap_references([_gap(evidence=["graph: ceramic path"])])
        assert any("ceramic path" in r for r in refs)

    def test_finding_key_not_added_as_entry(self) -> None:
        refs = build_gap_references([_gap(evidence=["[F3]", "graph: something"])])
        assert not any(r == "[F3]" for r in refs)

    def test_multiple_graph_citations_all_included(self) -> None:
        refs = build_gap_references([_gap(evidence=["graph: path A", "graph: path B"])])
        assert any("path A" in r for r in refs)
        assert any("path B" in r for r in refs)

    def test_empty_candidates_returns_empty(self) -> None:
        assert build_gap_references([]) == []

    def test_candidate_without_evidence_attr(self) -> None:
        class _Plain:
            title = "T"
            description = "D"

        refs = build_gap_references([_Plain()])  # type: ignore[arg-type]
        assert any("T" in r for r in refs)


# ---------------------------------------------------------------------------
# render_trail
# ---------------------------------------------------------------------------


class TestRenderTrail:
    def test_closing_summary_always_present(self) -> None:
        t = _transcript(_tool_chunk(1), _tool_chunk(2), _tool_chunk(3))
        scorer = _Scorer([0.9, 0.1, 0.1])
        result = asyncio.run(render_trail(t, ["ref"], scorer, budget=len(_tool_chunk(1)) + 20))
        assert "Closing summary." in result

    def test_min_chunks_floor_honoured(self) -> None:
        chunks = [_tool_chunk(i) for i in range(5)]
        t = "\n\n".join(chunks)
        scorer = _Scorer([0.0, 0.0, 0.0, 0.0, 0.0])
        result = asyncio.run(render_trail(t, ["ref"], scorer, budget=10, min_chunks=2))
        included = [c for c in chunks if c[:20] in result]
        assert len(included) >= _MIN_TRAIL_CHUNKS

    def test_elision_marker_counts_dropped_chunks(self) -> None:
        chunks = [_tool_chunk(i) for i in range(4)]
        t = "\n\n".join(chunks + ["summary"])
        scores = [0.9, 0.1, 0.1, 0.1]
        scorer = _Scorer(scores)
        budget = len(chunks[0]) + 20
        result = asyncio.run(render_trail(t, ["ref"], scorer, budget=budget, min_chunks=1))
        assert "elided" in result

    def test_chunk_selection_follows_scores(self) -> None:
        chunks = [_tool_chunk(1), _tool_chunk(2), _tool_chunk(3)]
        t = "\n\n".join(chunks + ["summary"])
        scores = [0.1, 0.9, 0.1]
        scorer = _Scorer(scores)
        budget = len(chunks[0]) + 20
        result = asyncio.run(render_trail(t, ["ref"], scorer, budget=budget, min_chunks=1))
        assert "q2" in result

    def test_fail_open_on_scoring_error(self) -> None:
        chunks = [_tool_chunk(i) for i in range(3)]
        t = "\n\n".join(chunks + ["summary"])
        result = asyncio.run(render_trail(t, ["ref"], _FailScorer(), budget=_TRAIL_BUDGET_CHARS))
        assert result != ""
        assert "q1" in result

    def test_empty_references_uses_first_n(self) -> None:
        chunks = [_tool_chunk(i) for i in range(3)]
        t = "\n\n".join(chunks)
        result = asyncio.run(render_trail(t, [], _ZeroScorer(), budget=_TRAIL_BUDGET_CHARS))
        assert "q1" in result

    def test_no_tool_chunks_returns_transcript(self) -> None:
        result = asyncio.run(render_trail("plain text", ["ref"], _ZeroScorer()))
        assert result == "plain text"


# ---------------------------------------------------------------------------
# _select_by_score
# ---------------------------------------------------------------------------


class TestSelectByScore:
    def test_highest_scored_chunk_selected_first(self) -> None:
        chunks = [_tool_chunk(i) for i in range(3)]
        scores = [0.1, 0.9, 0.1]
        budget = len(chunks[1]) + 10
        idx = _select_by_score(chunks, scores, budget, min_n=1)
        assert 1 in idx

    def test_min_n_floor_even_with_zero_budget(self) -> None:
        chunks = [_tool_chunk(i) for i in range(3)]
        scores = [0.5, 0.4, 0.3]
        idx = _select_by_score(chunks, scores, budget=0, min_n=2)
        assert len(idx) >= 2


# ---------------------------------------------------------------------------
# _assemble_list and _assemble_indexed elision markers
# ---------------------------------------------------------------------------


class TestElisionMarkers:
    def test_elision_count_in_assemble_list(self) -> None:
        chunks = [_tool_chunk(1)]
        result = _assemble_list(chunks, "summary", total_tool_count=3)
        assert "2 tool results elided" in result

    def test_singular_elision_marker(self) -> None:
        chunks = [_tool_chunk(1), _tool_chunk(2)]
        result = _assemble_list(chunks, "summary", total_tool_count=3)
        assert "1 tool result elided" in result

    def test_no_elision_when_all_selected(self) -> None:
        chunks = [_tool_chunk(1), _tool_chunk(2)]
        result = _assemble_list(chunks, "", total_tool_count=2)
        assert "elided" not in result

    def test_inline_elision_between_selected_chunks(self) -> None:
        chunks = [_tool_chunk(i) for i in range(4)]
        selected = {0, 3}
        result = _assemble_indexed(chunks, selected, "summary")
        assert "2 tool results elided" in result
        assert chunks[0][:10] in result
        assert chunks[3][:10] in result


# ---------------------------------------------------------------------------
# format_findings truncation marker
# ---------------------------------------------------------------------------


class TestFormatFindingsTruncation:
    def test_truncation_marker_added_when_over_limit(self) -> None:
        findings = [_finding(f"Title {'x' * 400} {i}") for i in range(60)]
        text = format_findings(findings)
        assert len(text) <= _MAX_FINDINGS_CHARS + len("\n[truncated]")
        assert text.endswith("[truncated]")

    def test_no_marker_when_within_limit(self) -> None:
        text = format_findings([_finding("Short")])
        assert "[truncated]" not in text

    def test_empty_findings_placeholder_unchanged(self) -> None:
        assert format_findings([]) == "(no research findings)"


# ---------------------------------------------------------------------------
# build_exploration_context per-channel behaviour
# ---------------------------------------------------------------------------


class TestBuildExplorationContextA2:
    def test_roles_with_no_findings_excluded(self) -> None:
        result = asyncio.run(
            build_exploration_context({"role_a", "role_b"}, {"role_b": "text"}, {}, _ZeroScorer())
        )
        assert "role_a" not in result
        assert "role_b" in result

    def test_empty_roles_returns_empty(self) -> None:
        result = asyncio.run(build_exploration_context(set(), {}, {}, _ZeroScorer()))
        assert result == ""

    def test_per_role_trail_rendered(self) -> None:
        trail = _transcript(_tool_chunk(1))
        result = asyncio.run(
            build_exploration_context({"role_a"}, {"role_a": trail}, {}, _ZeroScorer())
        )
        assert "Exploration by role_a" in result
