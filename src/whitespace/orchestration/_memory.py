"""Cross-run memory assembly — what earlier runs teach the current one.

Loads prior output, rejections, executed queries and stored findings
from the session store and shapes them for the councils: reruns never
repeat paid-for searches, never resurface shipped results, and never
resurrect candidates discarded for grounded reasons. A fresh start
simply skips loading any of this.
"""

from __future__ import annotations

import logging

from whitespace.orchestration._research_stage import RunMemory
from whitespace.store.base import SessionStore

logger = logging.getLogger(__name__)

_MAX_MEMORY_ITEMS = 40


async def load_gap_memory(store: SessionStore | None) -> RunMemory:
    """Assemble everything the gap run should remember from earlier runs."""
    if store is None:
        return RunMemory()
    prior_needs = await store.get_all_previous_needs()
    discards = await store.list_discards("gap")
    findings = await store.list_raw_findings()

    queries: list[str] = []
    for f in findings:
        if f.query not in queries:
            queries.append(f.query)

    lines = [
        f"- [previously surfaced] {n.title}: {n.description}"
        for n in prior_needs[:_MAX_MEMORY_ITEMS]
    ]
    lines += [
        f"- [previously rejected: {d['reason']}] {d['title']}: {d['description']}"
        for d in discards[:_MAX_MEMORY_ITEMS]
    ]
    texts = [f"{n.title}: {n.description}" for n in prior_needs] + [
        f"{d['title']}: {d['description']}" for d in discards
    ]
    if prior_needs or discards or findings:
        logger.info(
            "load_gap_memory: %d prior needs, %d discards, %d findings, %d queries",
            len(prior_needs),
            len(discards),
            len(findings),
            len(queries),
        )
    return RunMemory(
        prior_queries=queries,
        prior_findings=findings,
        memory="\n".join(lines),
        prior_texts=texts,
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
