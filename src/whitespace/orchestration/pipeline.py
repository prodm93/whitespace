"""Top-level pipeline coordinator: owns all four LangGraph subgraphs."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from whitespace.agents.context_agent import ContextAgent
from whitespace.agents.profile_agent import ProfileAgent
from whitespace.config import Config
from whitespace.domain import IngestResult
from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.graph.neo4j_client import Neo4jClient
from whitespace.models.router import ModelRouter
from whitespace.orchestration._memory import load_gap_memory, load_ideation_negatives
from whitespace.orchestration._pipeline_lifecycle import PipelineLifecycleMixin
from whitespace.orchestration._pipeline_questions import PipelineQuestionsMixin
from whitespace.orchestration._research_stage import RunMemory
from whitespace.orchestration._run_records import save_gap_result, save_idea_result
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.orchestration.ingest_graph import IngestGraph
from whitespace.orchestration.query_graph import QueryGraph
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.store.base import SessionStore
from whitespace.tools.dedup import SemanticDeduplicator

if TYPE_CHECKING:
    from whitespace.orchestration._question_runs import QuestionRuns
    from whitespace.orchestration._shared_clients import SharedClients

logger = logging.getLogger(__name__)

_IDEATION_QUERY = "Retrieve patent landscape context for ideation on unmet needs"


class Pipeline(PipelineLifecycleMixin, PipelineQuestionsMixin):
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
        question_runs: QuestionRuns | None = None,
        owns_shared: bool = True,
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
        self._question_runs = question_runs
        self._owns_shared = owns_shared

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

    @classmethod
    def from_shared(
        cls,
        shared: SharedClients,
        config: Config,
        *,
        registry_path: Path | None = None,
        session_store: SessionStore | None = None,
    ) -> Pipeline:
        """Build a pipeline for one run on kept clients; it does not open or close them."""
        from whitespace.orchestration._wiring import build_run_pipeline

        return build_run_pipeline(
            cls, config, shared, registry_path, session_store, owns_shared=False
        )

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
        """Run the full gap analysis: the HITL interrupt point.

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
        needs, discards = await self._gap_council.run(
            profile,
            domain,
            doc_paths,
            keep_findings=keep_findings,
            run_id=run_id,
            run_memory=memory,
        )
        await save_gap_result(self._store, run_id, domain, needs, discards)
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
        """Run ideation council: resumes after the HITL interrupt.

        Prior proposals and rejected ideas are injected as negative
        examples unless ``fresh_start`` is set; discards are persisted
        so no rerun resurrects them.
        """
        logger.info("Pipeline.ideate: %d selected needs", len(selected_needs))
        run_id = run_id or str(uuid.uuid4())
        context = await self._ideation_context(fresh_start)
        proposals, discards = await self._ideation_council.run(
            selected_needs,
            context,
            profile,
        )
        titles = [n.title for n in selected_needs]
        await save_idea_result(self._store, run_id, gap_run_id, titles, proposals, discards)
        return proposals

    async def _ideation_context(self, fresh_start: bool) -> str:
        """Graph context for ideation, plus earlier proposals and rejections unless fresh."""
        context = await self._context_agent.run(_IDEATION_QUERY)
        if not fresh_start:
            context += await load_ideation_negatives(self._store)
        return context

    async def query(self, question: str) -> str:
        return await self._query.run(question)

    @property
    def router(self) -> ModelRouter:
        """The shared model router, for agents composed on top of the pipeline."""
        return self._router
