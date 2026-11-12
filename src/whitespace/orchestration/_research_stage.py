"""Pre-council research stage: execute queries, dedup, store, ingest.

Pure coordination. Query crafting stays with the identifiers, judgment
stays with the council.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, TypeVar

from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.orchestration._prior_output_gate import gate_against_prior
from whitespace.orchestration.ingest_graph import IngestGraph
from whitespace.schemas.critique import CandidateLike
from whitespace.schemas.research import RawFinding
from whitespace.store.base import SessionStore
from whitespace.tools.dedup import SemanticDeduplicator
from whitespace.tools.normaliser import Normaliser

logger = logging.getLogger(__name__)

C = TypeVar("C", bound=CandidateLike)

_MAX_FINDINGS_CHARS = 20000


@dataclass
class RunMemory:
    """What previous runs contribute to this one: queries not to repeat,
    findings not to re-buy, prior output not to resurface."""

    prior_queries: list[str] = field(default_factory=list)
    prior_findings: list[RawFinding] = field(default_factory=list)
    memory: str = ""
    prior_texts: list[str] = field(default_factory=list)
    neighbours: str = ""

    def to_dict(self) -> dict[str, Any]:
        """JSON-compatible form for carrying the memory across a paused run."""
        data = asdict(self)
        data["prior_findings"] = [f.model_dump(mode="json") for f in self.prior_findings]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunMemory:
        findings = [RawFinding.model_validate(f) for f in data["prior_findings"]]
        return cls(**{**data, "prior_findings": findings})


def format_finding_line(index: int, finding: RawFinding) -> str:
    """One dated finding of the raw-evidence channel, keyed [F{index}]."""
    return (
        f"- [F{index}] [{finding.source_type}] {finding.title}"
        f" ({finding.published or 'n.d.'}; found {finding.found_at:%Y-%m-%d};"
        f" query: {finding.query}): {finding.content[:400]}"
    )


def format_findings(findings: list[RawFinding]) -> str:
    """Render dated findings with stable [F{i}] keys for the raw-evidence channel."""
    lines = [format_finding_line(i, f) for i, f in enumerate(findings, 1)]
    joined = "\n".join(lines)
    if not joined:
        return "(no research findings)"
    if len(joined) > _MAX_FINDINGS_CHARS:
        return joined[:_MAX_FINDINGS_CHARS] + "\n[truncated]"
    return joined


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

    @property
    def deduplicator(self) -> SemanticDeduplicator:
        return self._dedup

    async def research(
        self,
        queries: list[str],
        *,
        domain: str,
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
        raw = await self._prior_art.research(fresh_queries)
        norm_domain = domain.strip().lower()
        new_findings = [f.model_copy(update={"domain": norm_domain}) for f in raw]
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
        domain: str = "",
    ) -> tuple[list[C], dict[str, str]]:
        """Score candidates against previous runs' output; kill duplicates, flag near-matches.

        Returns the surviving pool and a flags dict mapping candidate IDs
        to a note for the critic when a candidate is in the grey zone.
        """
        kept, flags, kill_items = await gate_against_prior(self._dedup, pool, prior_texts)
        kill_items = [{**item, "domain": domain} for item in kill_items]
        if kill_items:
            await self.record_discards(run_id, kind, kill_items, domain)
            logger.info("ResearchStage: gated %d cross-run duplicates", len(kill_items))
        return kept, flags

    async def record_discards(
        self, run_id: str, kind: str, items: list[dict[str, str]], domain: str = ""
    ) -> None:
        if self._store is not None and items:
            await self._store.save_discards(run_id, kind, items)

    async def ingest(self, doc_paths: list[str], findings: list[RawFinding]) -> None:
        """One graph build: user documents and research findings together."""
        documents = [self._normaliser.from_finding(f) for f in findings]
        await self._ingest.run(doc_paths, documents=documents)
