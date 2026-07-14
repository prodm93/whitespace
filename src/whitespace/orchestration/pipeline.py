"""Top-level pipeline coordinator — owns all four LangGraph subgraphs."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from whitespace.agents.context_agent import ContextAgent
from whitespace.agents.profile_agent import ProfileAgent
from whitespace.config import Config
from whitespace.domain import IngestResult
from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.graph.neo4j_client import Neo4jClient
from whitespace.models.router import ModelRouter
from whitespace.orchestration._memory import load_gap_memory, load_ideation_negatives
from whitespace.orchestration._research_stage import RunMemory
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.orchestration.ingest_graph import IngestGraph
from whitespace.orchestration.query_graph import QueryGraph
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.store.base import GapRun, IdeaRun, SessionStore
from whitespace.tools.dedup import SemanticDeduplicator

logger = logging.getLogger(__name__)

_IDEATION_QUERY = "Retrieve patent landscape context for ideation on unmet needs"


class Pipeline:
    """Top-level coordinator for the full ideation flow.

    Human-in-the-loop interrupt sits at the method boundary:
    ``analyse_gaps()`` returns unmet needs; the caller presents them,
    collects user selections, then passes them to :meth:`ideate`.
    """

    def __init__(
        self,
        *,
        config: Config,
        neo4j: Neo4jClient,
        graphiti: GraphitiClient,
        context_agent: ContextAgent,
        profile_agent: ProfileAgent,
        ingest_graph: IngestGraph,
        gap_council: GapCouncilGraph,
        ideation_council: IdeationCouncilGraph,
        query_graph: QueryGraph,
        router: ModelRouter,
        dedup: SemanticDeduplicator,
        session_store: SessionStore | None = None,
    ) -> None:
        self._config = config
        self._neo4j = neo4j
        self._graphiti = graphiti
        self._context_agent = context_agent
        self._profile_agent = profile_agent
        self._ingest = ingest_graph
        self._gap_council = gap_council
        self._ideation_council = ideation_council
        self._query = query_graph
        self._router = router
        self._dedup = dedup
        self._store = session_store

    @classmethod
    def from_config(
        cls,
        config: Config,
        *,
        registry_path: Path | None = None,
        session_store: SessionStore | None = None,
    ) -> Pipeline:
        """Wire all dependencies from a single Config object."""
        from whitespace.orchestration._wiring import _build_pipeline

        return _build_pipeline(cls, config, registry_path, session_store)

    async def initialise(self) -> None:
        """Connect Neo4j and initialise Graphiti. Call before any run."""
        await self._neo4j.connect()
        await self._graphiti.initialise()

    async def close(self) -> None:
        await self._graphiti.close()
        await self._neo4j.close()

    async def __aenter__(self) -> Self:
        await self.initialise()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def extract_profile(self, doc_paths: list[str]) -> ProfessionalProfile:
        logger.info("Pipeline.extract_profile: %d documents", len(doc_paths))
        return await self._profile_agent.run(doc_paths)

    async def ingest(self, doc_paths: list[str]) -> IngestResult:
        """Direct document ingestion (no research pass)."""
        logger.info("Pipeline.ingest: %d documents", len(doc_paths))
        return await self._ingest.run(doc_paths)

    async def analyse_gaps(
        self,
        profile: ProfessionalProfile,
        domain: str,
        doc_paths: list[str] | None = None,
        *,
        keep_findings: bool = False,
        run_id: str | None = None,
        fresh_start: bool = False,
    ) -> list[UnmetNeed]:
        """Run the full gap analysis — the HITL interrupt point.

        Reruns load cross-run memory (executed queries, stored findings,
        prior and rejected gaps) unless ``fresh_start`` is set. Results
        are persisted so reloads rehydrate instead of re-running.
        """
        logger.info("Pipeline.analyse_gaps: domain=%r fresh=%s", domain, fresh_start)
        run_id = run_id or str(uuid.uuid4())
        if fresh_start:
            memory = RunMemory()
        else:
            memory = await load_gap_memory(self._store, domain, self._dedup)
        needs = await self._gap_council.run(
            profile,
            domain,
            doc_paths,
            keep_findings=keep_findings,
            run_id=run_id,
            run_memory=memory,
        )
        if self._store is not None and needs:
            await self._store.save_gap_run(
                GapRun(
                    run_id=run_id,
                    timestamp=datetime.now(UTC),
                    needs=needs,
                    domain=domain.strip().lower(),
                )
            )
        return needs

    async def ideate(
        self,
        selected_needs: list[UnmetNeed],
        profile: ProfessionalProfile,
        *,
        run_id: str | None = None,
        gap_run_id: str = "",
        fresh_start: bool = False,
    ) -> list[IdeationProposal]:
        """Run ideation council — resumes after the HITL interrupt.

        Prior proposals and rejected ideas are injected as negative
        examples unless ``fresh_start`` is set; discards are persisted
        so no rerun resurrects them.
        """
        logger.info("Pipeline.ideate: %d selected needs", len(selected_needs))
        run_id = run_id or str(uuid.uuid4())
        context = await self._context_agent.run(_IDEATION_QUERY)
        if not fresh_start:
            context += await load_ideation_negatives(self._store)
        proposals, discards = await self._ideation_council.run(
            selected_needs,
            context,
            profile,
        )
        if self._store is not None:
            await self._store.save_discards(run_id, "idea", discards)
            if proposals:
                await self._store.save_idea_run(
                    IdeaRun(
                        run_id=run_id,
                        gap_run_id=gap_run_id,
                        selected_need_titles=[n.title for n in selected_needs],
                        timestamp=datetime.now(UTC),
                        proposals=proposals,
                    )
                )
        return proposals

    async def query(self, question: str) -> str:
        return await self._query.run(question)

    @property
    def router(self) -> ModelRouter:
        """The shared model router, for agents composed on top of the pipeline."""
        return self._router
