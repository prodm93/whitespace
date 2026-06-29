"""Top-level pipeline coordinator — owns all four LangGraph subgraphs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Self

from whitespace.agents.context_agent import ContextAgent
from whitespace.config import Config
from whitespace.domain import IngestResult
from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.graph.neo4j_client import Neo4jClient
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.orchestration.ingest_graph import IngestGraph
from whitespace.orchestration.query_graph import QueryGraph
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

_GAP_QUERY = "Identify limitations, gaps, and unmet needs in the patent landscape"
_IDEATION_QUERY = "Retrieve patent landscape context for ideation on unmet needs"


class Pipeline:
    """Top-level coordinator for the full ideation flow.

    Human-in-the-loop interrupt sits at the method boundary:
    ``analyse_gaps()`` returns unmet needs; the caller presents them,
    collects user selections, then passes them to ``ideate()``.
    """

    def __init__(
        self,
        *,
        config: Config,
        neo4j: Neo4jClient,
        graphiti: GraphitiClient,
        context_agent: ContextAgent,
        ingest_graph: IngestGraph,
        gap_council: GapCouncilGraph,
        ideation_council: IdeationCouncilGraph,
        query_graph: QueryGraph,
    ) -> None:
        self._config = config
        self._neo4j = neo4j
        self._graphiti = graphiti
        self._context_agent = context_agent
        self._ingest = ingest_graph
        self._gap_council = gap_council
        self._ideation_council = ideation_council
        self._query = query_graph

    @classmethod
    def from_config(
        cls,
        config: Config,
        *,
        registry_path: Path | None = None,
    ) -> Pipeline:
        """Wire all dependencies from a single Config object."""
        return _build_pipeline(cls, config, registry_path)

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

    async def ingest(self, doc_paths: list[str]) -> IngestResult:
        logger.info("Pipeline.ingest: %d documents", len(doc_paths))
        return await self._ingest.run(doc_paths)

    async def analyse_gaps(
        self,
        profile: ProfessionalProfile,
    ) -> list[UnmetNeed]:
        """Run gap council — the HITL interrupt point.

        Returns fleshed-out unmet needs for the caller to present to
        the user. The user selects which needs to develop, then the
        caller passes the selections to :meth:`ideate`.
        """
        logger.info("Pipeline.analyse_gaps: retrieving graph context")
        context = await self._context_agent.run(_GAP_QUERY)
        return await self._gap_council.run(context, profile)

    async def ideate(
        self,
        selected_needs: list[UnmetNeed],
        profile: ProfessionalProfile,
    ) -> list[IdeationProposal]:
        """Run ideation council — resumes after the HITL interrupt."""
        logger.info("Pipeline.ideate: %d selected needs", len(selected_needs))
        context = await self._context_agent.run(_IDEATION_QUERY)
        return await self._ideation_council.run(
            selected_needs,
            context,
            profile,
        )

    async def query(self, question: str) -> str:
        return await self._query.run(question)


def _build_pipeline(
    cls: type[Pipeline],
    config: Config,
    registry_path: Path | None,
) -> Pipeline:
    from whitespace.agents.council.gap_critic import GapCritic
    from whitespace.agents.council.gap_ideator import GapIdeator
    from whitespace.agents.council.gap_synthesiser import GapSynthesiser
    from whitespace.agents.council.idea_critic import IdeaCritic
    from whitespace.agents.council.idea_ideator import IdeaIdeator
    from whitespace.agents.council.idea_synthesiser import IdeaSynthesiser
    from whitespace.agents.council.prior_art_agent import PriorArtAgent
    from whitespace.agents.generator_agent import GeneratorAgent
    from whitespace.agents.graph_agent import GraphAgent
    from whitespace.agents.ontology_agent import OntologyAgent
    from whitespace.agents.retrieval_planner_agent import RetrievalPlannerAgent
    from whitespace.models.providers import ProviderFactory
    from whitespace.models.registry import ModelRegistry
    from whitespace.models.router import ModelRouter
    from whitespace.observability.cost_tracker import CostTracker
    from whitespace.observability.langsmith import configure_tracing_env
    from whitespace.observability.local_metrics import LocalMetricsEmitter
    from whitespace.observability.metrics import MetricsEmitter
    from whitespace.playbook import PLAYBOOK
    from whitespace.tools.document_loader import DocumentLoader
    from whitespace.tools.graph_tools import GraphTools
    from whitespace.tools.search.scholar_client import ScholarClient
    from whitespace.tools.search.uspto_client import UsptpClient

    configure_tracing_env(config)

    if registry_path is None:
        registry_path = Path(__file__).resolve().parents[3] / "model_registry.yaml"

    neo4j = Neo4jClient(config)
    graphiti = GraphitiClient(config, neo4j)
    registry = ModelRegistry(registry_path)
    provider_factory = ProviderFactory(config)
    emitter: MetricsEmitter
    if config.mode == "saas":
        from whitespace.observability.cloudwatch_metrics import CloudWatchMetricsEmitter

        emitter = CloudWatchMetricsEmitter()
    else:
        emitter = LocalMetricsEmitter()
    router = ModelRouter(registry, provider_factory, CostTracker(emitter))
    loader = DocumentLoader()
    graph_tools = GraphTools(graphiti, neo4j)

    ontology_agent = OntologyAgent(config, router, loader)
    graph_agent = GraphAgent(config, graphiti, loader)
    planner = RetrievalPlannerAgent(router, PLAYBOOK)
    context_agent = ContextAgent(config, graph_tools, planner)
    generator = GeneratorAgent(router)

    gap_ideators = [GapIdeator(config, router, f"gap_ideator_{i}") for i in range(1, 4)]
    idea_ideators = [
        IdeaIdeator(config, router, "idea_ideator_technical", "technical_feasibility"),
        IdeaIdeator(config, router, "idea_ideator_commercial", "commercial_value"),
        IdeaIdeator(config, router, "idea_ideator_crossdomain", "cross_domain_transfer"),
    ]

    return cls(
        config=config,
        neo4j=neo4j,
        graphiti=graphiti,
        context_agent=context_agent,
        ingest_graph=IngestGraph(ontology_agent, graph_agent),
        gap_council=GapCouncilGraph(
            gap_ideators,
            GapCritic(config, router),
            GapSynthesiser(config, router),
        ),
        ideation_council=IdeationCouncilGraph(
            idea_ideators,
            IdeaCritic(config, router),
            IdeaSynthesiser(config, router),
            PriorArtAgent(config, router, UsptpClient(), ScholarClient()),
        ),
        query_graph=QueryGraph(context_agent, generator),
    )
