"""LangGraph for document ingestion: ontology inference → graph build."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from whitespace.agents.graph_agent import GraphAgent
from whitespace.agents.ontology_agent import OntologyAgent
from whitespace.domain import IngestResult
from whitespace.schemas.ontology import OntologyDefinition

logger = logging.getLogger(__name__)


class IngestState(TypedDict):
    doc_paths: list[str]
    ontology: OntologyDefinition
    ingest_result: IngestResult


class IngestGraph:
    """Linear pipeline: ontology_inference → graph_build → END."""

    def __init__(
        self,
        ontology_agent: OntologyAgent,
        graph_agent: GraphAgent,
    ) -> None:
        self._ontology_agent = ontology_agent
        self._graph_agent = graph_agent
        self._compiled = self._build()

    def _build(self) -> Any:
        builder = StateGraph(IngestState)
        builder.add_node("ontology_inference", self._run_ontology)
        builder.add_node("graph_build", self._run_graph_build)
        builder.set_entry_point("ontology_inference")
        builder.add_edge("ontology_inference", "graph_build")
        builder.add_edge("graph_build", END)
        return builder.compile()

    async def run(self, doc_paths: list[str]) -> IngestResult:
        """Execute the full ingest pipeline and return the result."""
        logger.info("IngestGraph: starting with %d documents", len(doc_paths))
        initial_state: IngestState = {
            "doc_paths": doc_paths,
            "ontology": OntologyDefinition(),
            "ingest_result": IngestResult(documents_processed=0),
        }
        final_state = await self._compiled.ainvoke(initial_state)
        result: IngestResult = final_state["ingest_result"]
        return result

    async def _run_ontology(self, state: IngestState) -> dict[str, Any]:
        ontology = await self._ontology_agent.run(state["doc_paths"])
        return {"ontology": ontology}

    async def _run_graph_build(self, state: IngestState) -> dict[str, Any]:
        result = await self._graph_agent.run(state["doc_paths"], state["ontology"])
        return {"ingest_result": result}
