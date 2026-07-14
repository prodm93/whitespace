"""Tests for hybrid gap memory: loader partitioning, gate routing, council graph helpers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from whitespace.orchestration._council_common import build_flag_evidence
from whitespace.orchestration._memory import load_gap_memory
from whitespace.orchestration._memory_scoring import _NEIGHBOUR_FLOOR
from whitespace.orchestration._research_stage import ResearchStage, RunMemory, format_findings
from whitespace.schemas.gap import CandidateGap, UnmetNeed
from whitespace.schemas.research import RawFinding
from whitespace.store.base import GapRun

_TS = datetime(2026, 7, 1, tzinfo=UTC)


def _need(title: str = "Gap title") -> UnmetNeed:
    return UnmetNeed(
        title=title,
        description=f"Description of {title}",
        current_state="current",
        why_unmet="unmet reason",
        matching_skills=["skill"],
    )


def _gap(candidate_id: str, title: str = "T", score: float = 0.0) -> CandidateGap:
    return CandidateGap(
        title=title,
        description=f"Description of {title}",
        source_model="m",
        candidate_id=candidate_id,
        source_role="role_a",
    )


def _finding(domain: str | None = "batteries") -> RawFinding:
    return RawFinding(
        title="Finding",
        content="content",
        source_type="paper",
        source_name="src",
        query="query text",
        found_at=_TS,
        domain=domain,
    )


def _mock_store(
    gap_runs: list[GapRun] | None = None,
    discards: list[dict] | None = None,
    findings: list[RawFinding] | None = None,
) -> MagicMock:
    store = MagicMock()
    store.list_gap_runs = AsyncMock(return_value=gap_runs or [])
    store.list_discards = AsyncMock(return_value=discards or [])
    store.list_raw_findings = AsyncMock(return_value=findings or [])
    store.save_discards = AsyncMock()
    return store


def _mock_scorer(scores: list[float]) -> MagicMock:
    scorer = MagicMock()
    scorer.score_against = AsyncMock(return_value=scores)
    return scorer


def _research_stage(score_with_best: list[tuple[float, str]]) -> ResearchStage:
    dedup = MagicMock()
    dedup.score_against_with_best = AsyncMock(return_value=score_with_best)
    return ResearchStage(
        prior_art=MagicMock(),
        deduplicator=dedup,
        normaliser=MagicMock(),
        ingest_graph=MagicMock(),
        store=_mock_store(),
    )


# ---------------------------------------------------------------------------
# Loader partitioning
# ---------------------------------------------------------------------------


class TestLoadGapMemoryPartitioning:
    def test_exact_domain_need_goes_to_memory(self) -> None:
        need = _need("Exact domain need")
        store = _mock_store(
            gap_runs=[GapRun(run_id="r1", timestamp=_TS, needs=[need], domain="batteries")]
        )
        mem = asyncio.run(load_gap_memory(store, "batteries", _mock_scorer([])))
        assert "Exact domain need" in mem.memory
        assert mem.neighbours == ""

    def test_other_domain_above_floor_goes_to_neighbours(self) -> None:
        need = _need("Robotics need")
        store = _mock_store(
            gap_runs=[GapRun(run_id="r1", timestamp=_TS, needs=[need], domain="robotics")]
        )
        scorer = _mock_scorer([0.90])
        mem = asyncio.run(load_gap_memory(store, "batteries", scorer))
        assert mem.memory == ""
        assert "Robotics need" in mem.neighbours
        assert "similarity 0.90" in mem.neighbours

    def test_other_domain_below_floor_excluded_from_neighbours(self) -> None:
        need = _need("Distant need")
        store = _mock_store(
            gap_runs=[GapRun(run_id="r1", timestamp=_TS, needs=[need], domain="other")]
        )
        mem = asyncio.run(load_gap_memory(store, "batteries", _mock_scorer([0.60])))
        assert mem.neighbours == ""

    def test_null_domain_run_is_candidate_for_neighbours(self) -> None:
        need = _need("Unknown domain need")
        store = _mock_store(
            gap_runs=[GapRun(run_id="r1", timestamp=_TS, needs=[need], domain=None)]
        )
        scorer = _mock_scorer([0.88])
        mem = asyncio.run(load_gap_memory(store, "batteries", scorer))
        assert "Unknown domain need" in mem.neighbours

    def test_exact_domain_discards_go_to_memory_not_neighbours(self) -> None:
        store = _mock_store(
            discards=[
                {"title": "Killed gap", "description": "d", "reason": "r", "domain": "batteries"}
            ]
        )
        mem = asyncio.run(load_gap_memory(store, "batteries", _mock_scorer([])))
        assert "Killed gap" in mem.memory
        assert mem.neighbours == ""

    def test_other_domain_finding_above_floor_appears_in_neighbours(self) -> None:
        finding = _finding(domain="robotics")
        store = _mock_store(findings=[finding])
        scorer = _mock_scorer([0.87])
        mem = asyncio.run(load_gap_memory(store, "batteries", scorer))
        assert "Finding" in mem.neighbours
        assert "similarity 0.87" in mem.neighbours

    def test_none_store_returns_empty_run_memory(self) -> None:
        mem = asyncio.run(load_gap_memory(None, "batteries", _mock_scorer([])))
        assert mem == RunMemory()

    def test_neighbours_sorted_descending_by_score(self) -> None:
        need_a = _need("Low sim need")
        need_b = _need("High sim need")
        store = _mock_store(
            gap_runs=[
                GapRun(run_id="r1", timestamp=_TS, needs=[need_a], domain="robotics"),
                GapRun(run_id="r2", timestamp=_TS, needs=[need_b], domain="sensors"),
            ]
        )
        scorer = _mock_scorer([0.87, 0.95])
        mem = asyncio.run(load_gap_memory(store, "batteries", scorer))
        # High sim should appear first
        idx_high = mem.neighbours.index("High sim need")
        idx_low = mem.neighbours.index("Low sim need")
        assert idx_high < idx_low

    def test_exact_findings_feed_prior_queries(self) -> None:
        finding = _finding(domain="batteries")
        finding = finding.model_copy(update={"query": "unique query for batteries"})
        store = _mock_store(findings=[finding])
        mem = asyncio.run(load_gap_memory(store, "batteries", _mock_scorer([])))
        assert "unique query for batteries" in mem.prior_queries

    def test_exact_findings_feed_prior_findings(self) -> None:
        finding = _finding(domain="batteries")
        store = _mock_store(findings=[finding])
        mem = asyncio.run(load_gap_memory(store, "batteries", _mock_scorer([])))
        assert finding in mem.prior_findings

    def test_provenance_label_includes_source_domain(self) -> None:
        need = _need("Cross domain idea")
        store = _mock_store(
            gap_runs=[GapRun(run_id="r1", timestamp=_TS, needs=[need], domain="aerospace")]
        )
        scorer = _mock_scorer([0.90])
        mem = asyncio.run(load_gap_memory(store, "batteries", scorer))
        assert "aerospace" in mem.neighbours


# ---------------------------------------------------------------------------
# Gate pool routing
# ---------------------------------------------------------------------------


class TestGatePool:
    def test_clean_pass_below_flag_floor(self) -> None:
        stage = _research_stage([(0.50, "old text")])
        pool = [_gap("role_a-1", "Clean gap")]
        kept, flags = asyncio.run(stage.gate_pool(pool, ["prior text"], "run1", "gap"))
        assert len(kept) == 1
        assert kept[0].candidate_id == "role_a-1"
        assert flags == {}

    def test_flag_in_grey_zone(self) -> None:
        stage = _research_stage([(0.90, "resembled prior")])
        pool = [_gap("role_a-1", "Flagged gap")]
        kept, flags = asyncio.run(stage.gate_pool(pool, ["prior text"], "run1", "gap"))
        assert len(kept) == 1
        assert "role_a-1" in flags
        assert "0.90" in flags["role_a-1"]
        assert "resembled prior" in flags["role_a-1"]

    def test_kill_at_or_above_kill_threshold(self) -> None:
        stage = _research_stage([(0.97, "old text")])
        pool = [_gap("role_a-1", "Duplicate gap")]
        stage._store = _mock_store()
        kept, flags = asyncio.run(stage.gate_pool(pool, ["prior text"], "run1", "gap", "batteries"))
        assert kept == []
        assert flags == {}

    def test_kill_recorded_as_discard(self) -> None:
        mock_store = _mock_store()
        stage = _research_stage([(0.96, "old")])
        stage._store = mock_store
        pool = [_gap("role_a-1", "Dup gap")]
        asyncio.run(stage.gate_pool(pool, ["prior text"], "run1", "gap", "batteries"))
        mock_store.save_discards.assert_called_once()
        args = mock_store.save_discards.call_args[0]
        assert args[2][0]["title"] == "Dup gap"
        assert args[2][0]["domain"] == "batteries"

    def test_boundary_exactly_at_flag_floor(self) -> None:
        stage = _research_stage([(_NEIGHBOUR_FLOOR, "match")])
        pool = [_gap("role_a-1")]
        kept, flags = asyncio.run(stage.gate_pool(pool, ["t"], "run1", "gap"))
        assert len(kept) == 1
        assert "role_a-1" in flags

    def test_boundary_exactly_at_kill_threshold(self) -> None:
        stage = _research_stage([(0.95, "match")])
        pool = [_gap("role_a-1")]
        stage._store = _mock_store()
        kept, flags = asyncio.run(stage.gate_pool(pool, ["t"], "run1", "gap"))
        assert kept == []

    def test_three_candidates_each_routing_correctly(self) -> None:
        stage = _research_stage(
            [
                (0.40, ""),  # pass
                (0.88, "old"),  # flag
                (0.97, "dup"),  # kill
            ]
        )
        stage._store = _mock_store()
        pool = [_gap("r-1", "Pass"), _gap("r-2", "Flag"), _gap("r-3", "Kill")]
        kept, flags = asyncio.run(stage.gate_pool(pool, ["t"], "run1", "gap", "batteries"))
        ids = {c.candidate_id for c in kept}
        assert "r-1" in ids
        assert "r-2" in ids
        assert "r-3" not in ids
        assert "r-2" in flags
        assert "r-1" not in flags

    def test_empty_prior_texts_passes_all(self) -> None:
        stage = _research_stage([])
        pool = [_gap("r-1"), _gap("r-2")]
        kept, flags = asyncio.run(stage.gate_pool(pool, [], "run1", "gap"))
        assert len(kept) == 2
        assert flags == {}

    def test_empty_pool_returns_empty(self) -> None:
        stage = _research_stage([])
        kept, flags = asyncio.run(stage.gate_pool([], ["prior"], "run1", "gap"))
        assert kept == []
        assert flags == {}


# ---------------------------------------------------------------------------
# build_flag_evidence
# ---------------------------------------------------------------------------


class TestBuildFlagEvidence:
    def test_empty_flags_returns_empty_string(self) -> None:
        assert build_flag_evidence({}) == ""

    def test_non_empty_flags_include_header(self) -> None:
        result = build_flag_evidence({"r-1": "resembles X (score 0.90): old text"})
        assert "## RESEMBLES PRIOR WORK" in result
        assert "r-1" in result
        assert "resembles X" in result

    def test_multiple_flags_all_listed(self) -> None:
        result = build_flag_evidence({"a-1": "note A", "b-2": "note B"})
        assert "a-1" in result
        assert "b-2" in result

    def test_no_resembles_section_when_flags_empty(self) -> None:
        assert "RESEMBLES" not in build_flag_evidence({})


# ---------------------------------------------------------------------------
# format_findings does not include RunMemory content
# ---------------------------------------------------------------------------


class TestFormatFindings:
    def test_format_findings_contains_only_finding_data(self) -> None:
        finding = _finding()
        text = format_findings([finding])
        assert "Finding" in text
        assert "neighbours" not in text.lower()

    def test_no_findings_returns_placeholder(self) -> None:
        assert format_findings([]) == "(no research findings)"


# ---------------------------------------------------------------------------
# Slot reservation (_apply_type_caps)
# ---------------------------------------------------------------------------


class TestApplyTypeCaps:
    def test_findings_cannot_fill_needs_slots(self) -> None:
        from whitespace.orchestration._memory_scoring import (
            _MAX_DISCARDS,
            _MAX_FINDINGS,
            _MAX_NEEDS,
            _apply_type_caps,
        )

        # 2 needs, 0 discards, 20 findings (all above floor)
        needs = [(0.9, "n1"), (0.88, "n2")]
        discards: list[tuple[float, str]] = []
        findings = [(0.87 - i * 0.001, f"f{i}") for i in range(20)]
        caps = [_MAX_NEEDS, _MAX_DISCARDS, _MAX_FINDINGS]
        result = _apply_type_caps([needs, discards, findings], caps)
        result_texts = [r for _, r in result]
        assert "n1" in result_texts
        assert "n2" in result_texts
        # Findings fill unused needs + discards slots; total capped at MAX_MEMORY_ITEMS
        assert len(result) <= _MAX_NEEDS + _MAX_DISCARDS + _MAX_FINDINGS

    def test_backfill_works_when_type_is_empty(self) -> None:
        from whitespace.orchestration._memory_scoring import _apply_type_caps

        # No discards; their 10 slots should go to findings
        needs = [(0.9, "n")]
        discards: list[tuple[float, str]] = []
        findings = [(0.88 - i * 0.001, f"f{i}") for i in range(20)]
        result = _apply_type_caps([needs, discards, findings], [15, 10, 15])
        # 1 need + 0 discards + up to 15 findings = up to 16 from primary slots
        # + 14 unused need slots + 10 unused discard slots backfilled from findings overflow
        # Total findings selected = min(15, 20) + backfill from overflow
        assert "n" in [r for _, r in result]
        # At least 11 findings should be present (primary 15 - 1 need blocker, but
        # needs has 1 item so 14 need slots unused; those backfill from findings overflow)
        finding_texts = [r for _, r in result if r.startswith("f")]
        assert len(finding_texts) >= 15

    def test_primary_slots_take_highest_score_per_type(self) -> None:
        from whitespace.orchestration._memory_scoring import _apply_type_caps

        # Caps fully consumed: 2 needs → cap 2, 1 discard → cap 1, 0 findings → cap 0
        # No unused slots, so no backfill. Only "high", "med", "d" should appear.
        needs = [(0.95, "high"), (0.88, "med"), (0.80, "low")]
        discards = [(0.91, "d")]
        findings: list[tuple[float, str]] = []
        result = _apply_type_caps([needs, discards, findings], [2, 1, 0])
        texts = [r for _, r in result]
        assert "high" in texts
        assert "med" in texts
        assert "d" in texts
        assert "low" not in texts
