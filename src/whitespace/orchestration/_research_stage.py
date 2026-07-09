"""Pre-council research stage: execute queries, dedup, store, ingest.

Pure coordination — query crafting stays with the identifiers, judgment
stays with the council.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TypeVar

from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.orchestration.ingest_graph import IngestGraph
from whitespace.schemas.critique import CandidateLike, CriticReport
from whitespace.schemas.research import RawFinding
from whitespace.store.base import SessionStore
from whitespace.tools.dedup import SemanticDeduplicator
from whitespace.tools.normaliser import Normaliser

logger = logging.getLogger(__name__)

C = TypeVar("C", bound=CandidateLike)


@dataclass
class RunMemory:
    """What previous runs contribute to this one: queries not to repeat,
    findings not to re-buy, prior output not to resurface."""

    prior_queries: list[str] = field(default_factory=list)
    prior_findings: list[RawFinding] = field(default_factory=list)
    memory: str = ""
    prior_texts: list[str] = field(default_factory=list)


_MAX_FINDINGS_CHARS = 20000


def format_findings(findings: list[RawFinding]) -> str:
    """Render dated findings as the raw-evidence channel for prompts."""
    lines = [
        f"- [{f.source_type}] {f.title} ({f.published or 'n.d.'}; found {f.found_at:%Y-%m-%d}"
        f"; query: {f.query}): {f.content[:400]}"
        for f in findings
    ]
    return "\n".join(lines)[:_MAX_FINDINGS_CHARS] or "(no research findings)"


class ResearchStage:
    """Runs the research pass and the single combined graph build."""

    def __init__(
        self,
        prior_art: PriorArtAgent,
        deduplicator: SemanticDeduplicator,
        normaliser: Normaliser,
        ingest_graph: IngestGraph,
        store: SessionStore | None = None,
    ) -> None:
        self._prior_art = prior_art
        self._dedup = deduplicator
        self._normaliser = normaliser
        self._ingest = ingest_graph
        self._store = store

    async def research(
        self,
        queries: list[str],
        *,
        keep_findings: bool,
        run_id: str,
        prior_queries: list[str] | None = None,
        prior_findings: list[RawFinding] | None = None,
    ) -> list[RawFinding]:
        """Execute queries, drop near-duplicates, optionally persist.

        Queries already executed in earlier runs are skipped (their
        findings arrive via ``prior_findings`` instead of being paid for
        again); only findings new to this run are persisted.
        """
        prior_findings = prior_findings or []
        already_run = {q.strip().lower() for q in (prior_queries or [])}
        fresh_queries = [q for q in queries if q.strip().lower() not in already_run]
        if len(fresh_queries) < len(queries):
            logger.info(
                "ResearchStage: skipping %d already-executed queries",
                len(queries) - len(fresh_queries),
            )
        new_findings = await self._prior_art.research(fresh_queries)
        pool = await self._dedup.dedup(prior_findings + new_findings)
        new_ids = {id(f) for f in new_findings}
        if keep_findings and self._store is not None:
            await self._store.save_raw_findings(run_id, [f for f in pool if id(f) in new_ids])
        return pool

    async def gate_pool(
        self,
        pool: list[C],
        prior_texts: list[str],
        run_id: str,
        kind: str,
    ) -> list[C]:
        """Drop candidates near-identical to previous runs' output; record them."""
        if not prior_texts or not pool:
            return pool
        mask = await self._dedup.novel_mask(
            [f"{c.title}: {c.description}" for c in pool], prior_texts
        )
        dropped = [c for c, keep in zip(pool, mask, strict=True) if not keep]
        if dropped:
            await self.record_discards(
                run_id,
                kind,
                [
                    {
                        "title": c.title,
                        "description": c.description,
                        "reason": "near-duplicate of a previous run's output",
                    }
                    for c in dropped
                ],
            )
            logger.info("ResearchStage: gated %d cross-run duplicates", len(dropped))
        return [c for c, keep in zip(pool, mask, strict=True) if keep]

    async def record_kills(
        self,
        report: CriticReport,
        pool: list[C],
        run_id: str,
        kind: str,
    ) -> None:
        """Persist critic kills with their objections so reruns avoid them."""
        by_id = {c.candidate_id: c for c in pool}
        items = [
            {
                "title": by_id[a.candidate_id].title,
                "description": by_id[a.candidate_id].description,
                "reason": a.objections or "killed by council critic",
            }
            for a in report.assessments
            if a.verdict == "kill" and a.candidate_id in by_id
        ]
        await self.record_discards(run_id, kind, items)

    async def record_discards(self, run_id: str, kind: str, items: list[dict[str, str]]) -> None:
        if self._store is not None and items:
            await self._store.save_discards(run_id, kind, items)

    async def ingest(self, doc_paths: list[str], findings: list[RawFinding]) -> None:
        """One graph build: user documents and research findings together."""
        documents = [self._normaliser.from_finding(f) for f in findings]
        await self._ingest.run(doc_paths, documents=documents)
