"""Retrieval plan emitted by :class:`RetrievalPlannerAgent`.

The planner LLM returns JSON conforming to :class:`RetrievalPlan`. Any
deviation (unknown strategy, missing required params, malformed JSON)
causes the planner caller to fall back to the deterministic edge-first
hybrid + rerank path.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Strategy = Literal[
    "gap_analysis",
    "skill_matching",
    "citation_chain",
    "entity_focused",
]


class RetrievalPlanParams(BaseModel):
    """Strategy-specific params."""

    entity_name: str | None = Field(
        default=None,
        description="Focal entity for entity_focused or citation_chain",
    )
    edge_type_filter: str | None = Field(
        default=None,
        description="Edge type to filter on (e.g. CITES for citation_chain)",
    )


class RetrievalPlan(BaseModel):
    strategy: Strategy = Field(..., description="The retrieval strategy to run")
    params: RetrievalPlanParams = Field(default_factory=RetrievalPlanParams)
    reason: str = Field(default="", description="One-line justification")
