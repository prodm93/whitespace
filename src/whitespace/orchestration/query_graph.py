"""LangGraph for graph-grounded Q&A: context retrieval → answer generation."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from whitespace.agents.context_agent import ContextAgent
from whitespace.agents.generator_agent import GeneratorAgent

logger = logging.getLogger(__name__)


class QueryState(TypedDict):
    query: str
    context: str
    answer: str


class QueryGraph:
    """Linear pipeline: context → generate → END."""

    def __init__(
        self,
        context_agent: ContextAgent,
        generator_agent: GeneratorAgent,
    ) -> None:
        self._context_agent = context_agent
        self._generator_agent = generator_agent
        self._compiled = self._build()

    def _build(self) -> Any:
        builder = StateGraph(QueryState)
        builder.add_node("context", self._run_context)
        builder.add_node("generate", self._run_generate)
        builder.set_entry_point("context")
        builder.add_edge("context", "generate")
        builder.add_edge("generate", END)
        return builder.compile()

    async def run(self, query: str) -> str:
        """Execute the query pipeline and return the answer."""
        logger.info("QueryGraph: answering %d-char query", len(query))
        initial_state: QueryState = {
            "query": query,
            "context": "",
            "answer": "",
        }
        final_state = await self._compiled.ainvoke(initial_state)
        result: str = final_state["answer"]
        return result

    async def _run_context(self, state: QueryState) -> dict[str, Any]:
        context = await self._context_agent.run(state["query"])
        return {"context": context}

    async def _run_generate(self, state: QueryState) -> dict[str, Any]:
        answer = await self._generator_agent.run(state["query"], state["context"])
        return {"answer": answer}
