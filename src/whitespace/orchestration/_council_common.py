"""Shared council-graph mechanics: ID assignment, delegation routing, resolution."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TypeVar

from whitespace.schemas.critique import CandidateLike, CriticReport
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

MAX_REVISION_ROUNDS = 2
SCORE_BAR = 5

C = TypeVar("C", bound=CandidateLike)


async def collect_batches(
    roles: list[str],
    tasks: Sequence[Awaitable[list[C]]],
    label: str,
) -> list[tuple[str, list[C]]]:
    """Gather per-role tasks, dropping failures with a warning."""
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    batches: list[tuple[str, list[C]]] = []
    for role, outcome in zip(roles, raw, strict=True):
        if isinstance(outcome, BaseException):
            logger.warning("%s: %s failed: %s", label, role, outcome)
            continue
        batches.append((role, outcome))
    return batches


def should_revise(report: CriticReport | None, revision_round: int) -> bool:
    """Whether the critic's verdicts demand a targeted revision round."""
    return bool(
        report is not None and report.delegations() and revision_round < MAX_REVISION_ROUNDS
    )


Reviser = Callable[
    [list[tuple[C, str]], str, ProfessionalProfile],
    Awaitable[list[C]],
]


async def run_targeted_revision(
    revisers: Mapping[str, Reviser[C]],
    report: CriticReport,
    pool: list[C],
    graph_context: str,
    profile: ProfessionalProfile,
    label: str,
) -> list[C]:
    """Re-invoke only the flagged originators, then swap revisions into the pool."""
    grouped = group_delegations(report, pool)
    roles = [role for role in grouped if role in revisers]
    tasks = [revisers[role](grouped[role], graph_context, profile) for role in roles]
    batches = await collect_batches(roles, tasks, label)
    revised = [candidate for _, batch in batches for candidate in batch]
    return replace_candidates(pool, revised)


def assign_candidate_ids(batches: list[tuple[str, list[C]]]) -> list[C]:
    """Flatten fan-out results into one pool with stable IDs and source roles."""
    pool: list[C] = []
    for role, candidates in batches:
        for i, candidate in enumerate(candidates, 1):
            candidate.candidate_id = f"{role}-{i}"
            candidate.source_role = role
            pool.append(candidate)
    return pool


def group_delegations(
    report: CriticReport,
    pool: list[C],
) -> dict[str, list[tuple[C, str]]]:
    """Group delegate_back candidates by originating role, with critic feedback."""
    by_id = {c.candidate_id: c for c in pool}
    grouped: dict[str, list[tuple[C, str]]] = {}
    for assessment in report.delegations():
        candidate = by_id.get(assessment.candidate_id)
        if candidate is None:
            continue
        feedback = assessment.feedback_for_originator or assessment.objections or ""
        grouped.setdefault(candidate.source_role, []).append((candidate, feedback))
    return grouped


def replace_candidates(pool: list[C], revised: list[C]) -> list[C]:
    """Swap revised candidates into the pool by ID, preserving pool order."""
    by_id = {c.candidate_id: c for c in revised}
    return [by_id.get(c.candidate_id, c) for c in pool]


def resolve_final(report: CriticReport) -> CriticReport:
    """Resolve unresolved delegate_back verdicts once revision rounds are spent.

    A pending candidate is kept if every score clears the bar, else killed —
    per the migration spec's guard-trip rule.
    """
    assessments = []
    promoted: list[str] = []
    for assessment in report.assessments:
        if assessment.verdict == "delegate_back":
            if assessment.scores and min(assessment.scores.values()) >= SCORE_BAR:
                assessment = assessment.model_copy(update={"verdict": "keep"})
                promoted.append(assessment.candidate_id)
                logger.info("resolve_final: %s promoted to keep", assessment.candidate_id)
            else:
                assessment = assessment.model_copy(update={"verdict": "kill"})
                logger.info("resolve_final: %s demoted to kill", assessment.candidate_id)
        assessments.append(assessment)
    absorbed = {
        merge_id
        for a in assessments
        if a.verdict in ("keep", "develop_self")
        for merge_id in a.merge_with
    }
    ranking = [cid for cid in report.ranking if cid not in absorbed]
    ranking += [cid for cid in promoted if cid not in ranking and cid not in absorbed]
    return CriticReport(assessments=assessments, ranking=ranking)
