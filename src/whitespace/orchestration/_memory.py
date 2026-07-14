"""Cross-run memory assembly — what earlier runs teach the current one.

Loads prior output, rejections, executed queries and stored findings from
the session store and shapes them for the councils. Query and finding memory
is exact-domain only: paid-for searches are not repeated within the same
domain. Cross-run memory from other domains travels in a labelled neighbour
channel so councils can judge relevance inline. A fresh start skips all of
this.
"""

from __future__ import annotations

import logging

from whitespace.orchestration._memory_scoring import (
    _render_neighbours,
    _score_neighbours,
)
from whitespace.orchestration._research_stage import RunMemory
from whitespace.store.base import SessionStore
from whitespace.tools.dedup import SemanticDeduplicator

logger = logging.getLogger(__name__)

_MAX_MEMORY_ITEMS = 40


def _normalise(domain: str | None) -> str:
    return domain.strip().lower() if domain else ""


async def load_gap_memory(
    store: SessionStore | None,
    domain: str,
    scorer: SemanticDeduplicator,
) -> RunMemory:
    """Assemble everything the gap run should remember from earlier runs.

    Prior items from the same domain feed the exact bucket; items from
    other domains are scored against the current domain string and, if
    above the neighbour floor, rendered into a labelled context block
    for the identifiers to judge inline.
    """
    if store is None:
        return RunMemory()

    norm_domain = _normalise(domain)
    gap_runs = await store.list_gap_runs()
    discards = await store.list_discards("gap")
    findings = await store.list_raw_findings()

    # Partition into exact-domain and candidate-neighbour buckets.
    exact_needs = [
        need for run in gap_runs if _normalise(run.domain) == norm_domain for need in run.needs
    ]
    exact_discards = [d for d in discards if _normalise(d.get("domain")) == norm_domain]
    exact_findings = [f for f in findings if _normalise(f.domain) == norm_domain]

    other_needs = [
        (run.domain, need)
        for run in gap_runs
        if _normalise(run.domain) != norm_domain
        for need in run.needs
    ]
    other_discards = [d for d in discards if _normalise(d.get("domain")) != norm_domain]
    other_findings = [f for f in findings if _normalise(f.domain) != norm_domain]

    if exact_needs or exact_discards or exact_findings:
        logger.info(
            "load_gap_memory: exact — %d needs, %d discards, %d findings",
            len(exact_needs),
            len(exact_discards),
            len(exact_findings),
        )

    # Build exact-bucket output.
    queries: list[str] = []
    for f in exact_findings:
        if f.query not in queries:
            queries.append(f.query)

    memory_lines = [
        f"- [previously surfaced] {n.title}: {n.description}"
        for n in exact_needs[:_MAX_MEMORY_ITEMS]
    ]
    memory_lines += [
        f"- [previously rejected: {d['reason']}] {d['title']}: {d['description']}"
        for d in exact_discards[:_MAX_MEMORY_ITEMS]
    ]
    prior_texts = [f"{n.title}: {n.description}" for n in exact_needs] + [
        f"{d['title']}: {d['description']}" for d in exact_discards
    ]

    # Score other-domain items against the current domain string.
    neighbour_items = await _score_neighbours(
        domain, other_needs, other_discards, other_findings, scorer
    )
    neighbour_block = _render_neighbours(neighbour_items)

    return RunMemory(
        prior_queries=queries,
        prior_findings=exact_findings,
        memory="\n".join(memory_lines),
        prior_texts=prior_texts,
        neighbours=neighbour_block,
    )


async def load_ideation_negatives(store: SessionStore | None) -> str:
    """Prior proposals and rejected ideas as a do-not-repeat block."""
    if store is None:
        return ""
    proposals = await store.get_all_previous_proposals()
    discards = await store.list_discards("idea")
    if not proposals and not discards:
        return ""
    lines = [
        f"- [already proposed] {p.title}: {p.problem_statement}"
        for p in proposals[:_MAX_MEMORY_ITEMS]
    ]
    lines += [
        f"- [previously rejected: {d['reason']}] {d['title']}: {d['description']}"
        for d in discards[:_MAX_MEMORY_ITEMS]
    ]
    return (
        "\n\n## ALREADY GENERATED OR REJECTED IDEAS\n\n"
        "Do NOT repeat or trivially vary any of these. Rejected entries "
        "include the reason; treat them as settled.\n\n" + "\n".join(lines)
    )
