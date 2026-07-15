"""Tool schema definitions for the orchestrator action surface."""

from typing import Any

_EMPTY: dict[str, Any] = {"type": "object", "properties": {}}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_status",
        "description": (
            "What the session currently holds: profile readiness, staged domain "
            "and documents, gap results, user selections, proposals. Call this first."
        ),
        "parameters": _EMPTY,
    },
    {
        "name": "extract_profile",
        "description": (
            "Extract a professional profile from the staged profile documents. "
            "Required before any analysis run if the profile is not ready."
        ),
        "parameters": _EMPTY,
    },
    {
        "name": "stage",
        "description": (
            "Record the domain string and keep_findings preference so "
            "run_gap_analysis knows what to research. Document paths are "
            "already staged by the upload endpoint."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Patent domain to research",
                },
                "keep_findings": {
                    "type": "boolean",
                    "description": "Persist raw research findings for future runs",
                },
            },
            "required": ["domain"],
        },
    },
    {
        "name": "run_gap_analysis",
        "description": (
            "Full gap analysis: researches the staged domain, builds the "
            "knowledge graph from user documents plus research, runs the gap "
            "council. Slow and costly; run at most once per job."
        ),
        "parameters": _EMPTY,
    },
    {
        "name": "run_ideation",
        "description": (
            "Develop the user's SELECTED gaps into invention proposals. "
            "Only valid for titles present in the user's confirmed sidecar; "
            "never select gaps on the user's behalf."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "selected_titles": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
            "required": ["selected_titles"],
        },
    },
    {
        "name": "query_knowledge_graph",
        "description": (
            "Answer a question from the knowledge graph (the user's "
            "background connected to the domain research)."
        ),
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
]
