"""Tests for critic report parsing and council revision-loop mechanics."""

from __future__ import annotations

import json

from whitespace.agents.council._critic_base import parse_critic_report
from whitespace.orchestration._council_common import (
    assign_candidate_ids,
    group_delegations,
    replace_candidates,
    resolve_final,
)
from whitespace.schemas.critique import CriticAssessment, CriticReport
from whitespace.schemas.gap import CandidateGap


def _gap(candidate_id: str = "", source_role: str = "", title: str = "t") -> CandidateGap:
    return CandidateGap(
        title=title,
        description="d",
        source_model="model-x",
        candidate_id=candidate_id,
        source_role=source_role,
    )


def _raw_report(assessments: list[dict[str, object]], ranking: list[str]) -> str:
    defaults: dict[str, object] = {
        "scores": {},
        "objections": None,
        "feedback_for_originator": None,
        "developed_description": None,
        "merge_with": [],
    }
    return json.dumps({"assessments": [defaults | a for a in assessments], "ranking": ranking})


def test_assign_candidate_ids_sets_ids_and_roles() -> None:
    pool = assign_candidate_ids(
        [("role_a", [_gap(), _gap()]), ("role_b", [_gap()])],
    )
    assert [c.candidate_id for c in pool] == ["role_a-1", "role_a-2", "role_b-1"]
    assert [c.source_role for c in pool] == ["role_a", "role_a", "role_b"]


def test_parse_repairs_missing_and_unknown_assessments() -> None:
    candidates = [_gap("a-1"), _gap("a-2")]
    content = _raw_report(
        [
            {"candidate_id": "a-1", "verdict": "keep"},
            {"candidate_id": "ghost", "verdict": "kill"},
        ],
        ["a-1", "ghost"],
    )
    report = parse_critic_report(content, candidates, "TestCritic")
    assert {a.candidate_id for a in report.assessments} == {"a-1", "a-2"}
    missing = report.assessment_for("a-2")
    assert missing is not None and missing.verdict == "keep"
    assert report.ranking == ["a-1", "a-2"]


def test_parse_excludes_merge_absorbed_from_ranking() -> None:
    candidates = [_gap("a-1"), _gap("a-2"), _gap("a-3")]
    content = _raw_report(
        [
            {"candidate_id": "a-1", "verdict": "keep", "merge_with": ["a-2"]},
            {"candidate_id": "a-2", "verdict": "keep"},
            {"candidate_id": "a-3", "verdict": "kill"},
        ],
        ["a-1", "a-2"],
    )
    report = parse_critic_report(content, candidates, "TestCritic")
    assert report.ranking == ["a-1"]


def test_group_delegations_routes_by_source_role() -> None:
    pool = [_gap("a-1", "role_a"), _gap("b-1", "role_b")]
    report = CriticReport(
        assessments=[
            CriticAssessment(
                candidate_id="a-1",
                verdict="delegate_back",
                feedback_for_originator="sharpen",
            ),
            CriticAssessment(candidate_id="b-1", verdict="keep"),
        ],
        ranking=["b-1"],
    )
    grouped = group_delegations(report, pool)
    assert list(grouped) == ["role_a"]
    ((candidate, feedback),) = grouped["role_a"]
    assert candidate.candidate_id == "a-1"
    assert feedback == "sharpen"


def test_replace_candidates_swaps_by_id_preserving_order() -> None:
    pool = [_gap("a-1"), _gap("a-2")]
    revised = [_gap("a-2", title="revised")]
    result = replace_candidates(pool, revised)
    assert [c.candidate_id for c in result] == ["a-1", "a-2"]
    assert result[1].title == "revised"


def test_resolve_final_promotes_and_demotes_by_score_bar() -> None:
    scores_good = {"novelty": 7, "specificity": 6}
    scores_bad = {"novelty": 7, "specificity": 3}
    report = CriticReport(
        assessments=[
            CriticAssessment(candidate_id="a-1", verdict="delegate_back", scores=scores_good),
            CriticAssessment(candidate_id="a-2", verdict="delegate_back", scores=scores_bad),
            CriticAssessment(candidate_id="a-3", verdict="keep"),
        ],
        ranking=["a-3"],
    )
    resolved = resolve_final(report)
    promoted = resolved.assessment_for("a-1")
    demoted = resolved.assessment_for("a-2")
    assert promoted is not None and promoted.verdict == "keep"
    assert demoted is not None and demoted.verdict == "kill"
    assert resolved.ranking == ["a-3", "a-1"]
