"""Constructs and wires the pipeline's dependencies from a Config."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from whitespace.agents.context_agent import ContextAgent
from whitespace.agents.profile_agent import ProfileAgent
from whitespace.config import Config
from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.graph.neo4j_client import Neo4jClient
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.orchestration.ingest_graph import IngestGraph
from whitespace.orchestration.query_graph import QueryGraph
from whitespace.store.base import SessionStore

if TYPE_CHECKING:
    from whitespace.orchestration.pipeline import Pipeline

logger = logging.getLogger(__name__)


def _build_pipeline(
    cls: type[Pipeline],
    config: Config,
    registry_path: Path | None,
    session_store: SessionStore | None,
) -> Pipeline:
    from whitespace.agents._graph_actions import GraphActions
    from whitespace.agents.council.gap_critic import GapCritic
    from whitespace.agents.council.gap_identifier import GapIdentifier
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
    from whitespace.orchestration._gap_snapshot import GapSnapshotWriter
    from whitespace.orchestration._research_stage import ResearchStage
    from whitespace.playbook import PLAYBOOK
    from whitespace.tools.dedup import SemanticDeduplicator
    from whitespace.tools.document_loader import DocumentLoader
    from whitespace.tools.graph_tools import GraphTools
    from whitespace.tools.normaliser import Normaliser
    from whitespace.tools.search.research_executor import ResearchExecutor
    from whitespace.tools.search.scholar_client import ScholarClient
    from whitespace.tools.search.uspto_client import UsptpClient
    from whitespace.tools.search.web_search import WebSearch

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
    profile_agent = ProfileAgent(config, router, loader)
    planner = RetrievalPlannerAgent(router, PLAYBOOK)
    context_agent = ContextAgent(config, graph_tools, planner)
    generator = GeneratorAgent(router)
    ingest_graph = IngestGraph(ontology_agent, graph_agent)

    executor = ResearchExecutor(
        UsptpClient(),
        ScholarClient(),
        WebSearch(exa_api_key=config.exa_api_key),
    )
    prior_art = PriorArtAgent(config, executor)
    graph_actions = GraphActions(config, graph_tools)
    gap_identifiers = [
        GapIdentifier(config, router, f"gap_identifier_{i}", graph_actions) for i in range(1, 4)
    ]
    idea_ideators = [IdeaIdeator(config, router, f"idea_ideator_{i}") for i in range(1, 4)]
    dedup = SemanticDeduplicator(graphiti)
    snapshot_writer = None
    if config.mode == "byok" and config.gap_snapshot_dir:
        snapshot_writer = GapSnapshotWriter(Path(config.gap_snapshot_dir))

    question_gate = None
    if config.mode == "byok" and session_store is not None:
        from whitespace.agents.council.question_gate import QuestionGate

        question_gate = QuestionGate(config, router, dedup, session_store)
    gap_council = GapCouncilGraph(
        gap_identifiers,
        GapCritic(config, router),
        GapSynthesiser(config, router),
        ResearchStage(prior_art, dedup, Normaliser(), ingest_graph, store=session_store),
        question_gate=question_gate,
        snapshot_writer=snapshot_writer,
    )
    ideation_council = IdeationCouncilGraph(
        idea_ideators,
        IdeaCritic(config, router),
        IdeaSynthesiser(config, router),
        prior_art,
        dedup,
        question_gate=question_gate,
    )
    question_runs = None
    if question_gate is not None and session_store is not None:
        from whitespace.orchestration._council_halves import GapHalves, IdeationHalves
        from whitespace.orchestration._question_pause import QuestionPauseShell
        from whitespace.orchestration._question_runs import QuestionRuns

        question_runs = QuestionRuns(
            session_store,
            QuestionPauseShell(config.question_checkpoint_db_path),
            GapHalves(gap_council),
            IdeationHalves(ideation_council),
        )

    return cls(
        config=config,
        neo4j=neo4j,
        graphiti=graphiti,
        context_agent=context_agent,
        profile_agent=profile_agent,
        ingest_graph=ingest_graph,
        gap_council=gap_council,
        ideation_council=ideation_council,
        query_graph=QueryGraph(context_agent, generator),
        router=router,
        dedup=dedup,
        session_store=session_store,
        question_runs=question_runs,
    )
