"""Prompt and response format for the adaptive question gate."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are the autonomous question gate for a multi-model patent council. Decide whether \
interrupting the user with any of the proposed questions would improve the council's work \
enough to justify the interruption.

Judge the value of each question in this run. Do not target a particular asking frequency. \
Reject questions that are unnecessary, banal, generic, already answered, disconnected from \
the discovered evidence, or unlikely to affect the work. Preserve questions that could \
meaningfully clarify the analysis or unlock a stronger candidate.

The engagement digest is context, not a leash. A cold start is not a reason for caution. \
Past skips do not automatically disqualify a strong question, and an exceptional unlock can \
outweigh a cautious engagement pattern. Prefer bold, useful judgment over mechanical \
consistency.

Exact duplicate questions have already been removed. When a similar past question appears, \
judge whether the present evidence or user context has genuinely shifted. Reject a mere \
rephrasing designed to evade the duplicate check.

If asking is worthwhile, select and rank the strongest proposals. You may merge overlapping \
proposals and author the final question, rationale, and hypothesis. Every selected question \
must cite its source proposal IDs. Keep each final question focused and answerable from the \
user's own knowledge. When unlock proposals exist and you decide to ask, include at least one \
unlock question. Explain the concrete judgment behind your decision.
"""

GATE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "AdaptiveQuestionGateDecision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "ask": {"type": "boolean"},
                "selected_questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_proposal_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "question": {"type": "string"},
                            "purpose": {
                                "type": "string",
                                "enum": ["clarify", "unlock"],
                            },
                            "rationale": {"type": "string"},
                            "hypothesis": {"type": "string"},
                        },
                        "required": [
                            "source_proposal_ids",
                            "question",
                            "purpose",
                            "rationale",
                            "hypothesis",
                        ],
                        "additionalProperties": False,
                    },
                },
                "ranked_proposal_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "reasoning": {"type": "string"},
            },
            "required": [
                "ask",
                "selected_questions",
                "ranked_proposal_ids",
                "reasoning",
            ],
            "additionalProperties": False,
        },
    },
}
