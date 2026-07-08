"""LangGraph for corpus ingestion: ontology inference → graph build."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from whitespace.agents.graph_agent import GraphAgent
from whitespace.agents.ontology_agent import OntologyAgent
from whitespace.domain import IngestResult
from whitespace.schemas.ontology import OntologyDefinition
from whitespace.schemas.patent import NormalisedDocument

logger = logging.getLogger(__name__)

_SAMPLE_CHARS = 2000


class IngestState(TypedDict):
    doc_paths: list[str]
    documents: list[NormalisedDocument]
    ontology: OntologyDefinition
    ingest_result: IngestResult


class IngestGraph:
    """Linear pipeline: ontology_inference → graph_build → END.

    Ingests uploaded files and normalised research documents in one
    build, so user background and the research landscape land in the
    same graph and can connect to each other.
    """

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

    async def run(
        self,
        doc_paths: list[str],
        documents: list[NormalisedDocument] | None = None,
    ) -> IngestResult:
        """Execute the full ingest pipeline and return the result."""
        documents = documents or []
        logger.info(
            "IngestGraph: starting with %d files, %d research documents",
            len(doc_paths),
            len(documents),
        )
        initial_state: IngestState = {
            "doc_paths": doc_paths,
            "documents": documents,
            "ontology": OntologyDefinition(),
            "ingest_result": IngestResult(documents_processed=0),
        }
        final_state = await self._compiled.ainvoke(initial_state)
        result: IngestResult = final_state["ingest_result"]
        return result

    async def _run_ontology(self, state: IngestState) -> dict[str, Any]:
        extra = [
            (doc.source_name, f"{doc.title}\n{doc.content}"[:_SAMPLE_CHARS])
            for doc in state["documents"]
        ]
        ontology = await self._ontology_agent.run(state["doc_paths"], extra_samples=extra)
        return {"ontology": ontology}

    async def _run_graph_build(self, state: IngestState) -> dict[str, Any]:
        result = await self._graph_agent.run(
            state["doc_paths"],
            state["ontology"],
            documents=state["documents"],
        )
        return {"ingest_result": result}
