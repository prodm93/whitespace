"""Generator agent — produces the final natural-language answer.

Calls the model router with a system prompt that grounds the answer
strictly in graph-derived context. When the context indicates no
results, returns a canned message rather than invoking the LLM.
"""

from __future__ import annotations

import logging

from whitespace.agents._context_helpers import EMPTY_CONTEXT
from whitespace.models.router import ModelRouter

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert analyst answering questions strictly grounded in a "
    "knowledge graph. You will receive a CONTEXT block extracted from the "
    "graph and a user QUESTION. Answer using ONLY information that appears "
    "in CONTEXT.\n"
    "\n"
    "Reasoning protocol (silent — do NOT emit it):\n"
    "  1. Scan the CONTEXT facts and identify which entities and edges are "
    "actually relevant to the question.\n"
    "  2. Assemble the answer from those edges. Note any gaps before you "
    "commit.\n"
    "  3. If a key piece is missing, name what's missing rather than "
    "inferring.\n"
    "\n"
    "Citation discipline: every non-trivial factual claim must reference the "
    "edge it came from, formatted exactly as `[SOURCE_ENTITY → EDGE_TYPE → "
    "TARGET_ENTITY]` using the entity names and edge type as they appear in "
    "the CONTEXT. Only entities present in CONTEXT may be cited. Do not "
    "invent entities, edge types, or relationships.\n"
    "\n"
    "Answer format by question type:\n"
    "  • Yes/no: lead with the verdict, then one supporting sentence with a "
    "citation.\n"
    "  • Factual lookup: 1-2 sentences, with citations.\n"
    "  • Analytical or comparative: a brief opening sentence then bullet "
    "points (each bullet cites its supporting edge).\n"
    "  • List request: just the list, one citation per item.\n"
    "\n"
    "Missing-information protocol: if CONTEXT does not contain enough to "
    "answer, say so plainly and name the specific piece that is missing "
    '(e.g. "the context shows X was approved but does not state the '
    'approval date"). Do not speculate. Do not fall back on general '
    "knowledge.\n"
    "\n"
    "Temporal handling: where an edge carries `valid from` / `invalid from` / "
    "`observed at` bounds in CONTEXT, respect those bounds in the answer. If "
    "the question is about the present and an edge is marked invalid, say "
    "so. Surface temporal bounds when they are material to the answer.\n"
    "\n"
    "Length: 4-10 sentences (or bullets) for analytical questions; 1-2 "
    "sentences for factual lookups; bullets only for analytical, comparative, "
    "or list requests."
)

_NO_CONTEXT_REPLY = (
    "I could not find anything relevant to your question in the "
    "knowledge graph yet. Try ingesting more documents or "
    "rephrasing the question."
)

_ERROR_REPLY = "An error occurred while generating the answer. Please retry in a moment."


class GeneratorAgent:
    """Produces the final answer from the user query and graph-derived context."""

    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    async def run(self, query: str, context: str) -> str:
        logger.info("GeneratorAgent: generating answer for %d-char query", len(query))
        if context.strip() == EMPTY_CONTEXT:
            return _NO_CONTEXT_REPLY

        try:
            result = await self._router.call(
                role="generator",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"CONTEXT:\n{context}\n\nQUESTION:\n{query}",
                    },
                ],
                temperature=0.0,
            )
        except Exception:
            logger.exception("GeneratorAgent: chat completion failed")
            return _ERROR_REPLY

        return (result["content"] or "").strip()
