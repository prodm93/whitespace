"""Prompts, response formats and the USER ANSWERS channel for refining with answers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from whitespace.agents.council._gap_prompts import _GAPS_SCHEMA
from whitespace.agents.council._idea_prompts import _IDEAS_SCHEMA
from whitespace.schemas.question import QuestionRecord, UserAnswer

GAP_REFINE_PROMPT = """\
You are a patent-landscape analyst. Earlier in this run you proposed candidate gaps. \
The user has now answered questions that the council asked. Their answers are in the \
section USER ANSWERS, keyed [Q1], [Q2], [Q3]. A skipped question tells you nothing; \
do not guess an answer for it.

Revise your own candidates in the light of the answers. Where an answer supports a \
candidate, make the candidate more specific and cite the answer by its key in the \
evidence list. Where an answer contradicts a candidate, correct the candidate or say \
plainly in its description what no longer holds. Where an answer changes nothing, \
return the candidate unchanged. Do not change the subject of a candidate.

If an answer opens a point that the research findings do not cover, you may request \
up to 3 new search queries in follow_up_queries. Request a query only when its result \
could change a candidate. Otherwise return an empty list.

Return exactly one gap per candidate, in the same order, with title, description and \
evidence. Keep citations that still hold.

If an answer points to a gap that none of your candidates covers, you may add up to \
2 new gaps in new_gaps. Each new gap must cite at least one answer key in its \
evidence list. Otherwise return an empty list.\
"""

IDEA_REFINE_PROMPT = """\
You are an inventor. Earlier in this run you proposed candidate ideas. The user has \
now answered questions that the council asked. Their answers are in the section USER \
ANSWERS, keyed [Q1], [Q2], [Q3]. A skipped question tells you nothing; do not guess \
an answer for it.

Revise your own ideas in the light of the answers. Where an answer makes an idea \
buildable or sharper, develop the idea and name the answer by its key in the \
description. Where an answer rules an idea out, say plainly in its description what \
no longer holds. Where an answer changes nothing, return the idea unchanged. Stay \
bold; do not weaken an idea for market or cost reasons.

Return exactly one idea per candidate, in the same order, with the same output shape.

If an answer points to an idea that none of your candidates covers, you may add up \
to 2 new ideas in new_ideas. Each new idea must name at least one answer key in its \
description. Otherwise return an empty list.\
"""

GAP_REFINE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "RefinedCandidateGaps",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "gaps": _GAPS_SCHEMA,
                "new_gaps": _GAPS_SCHEMA,
                "follow_up_queries": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["gaps", "new_gaps", "follow_up_queries"],
            "additionalProperties": False,
        },
    },
}

IDEA_REFINE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "RefinedCandidateIdeas",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"ideas": _IDEAS_SCHEMA, "new_ideas": _IDEAS_SCHEMA},
            "required": ["ideas", "new_ideas"],
            "additionalProperties": False,
        },
    },
}

_HEADER = "## USER ANSWERS (this run)"
_SKIPPED = "(the user skipped this question)"


def render_user_answers(records: list[QuestionRecord], answers: list[UserAnswer]) -> str:
    """Render the asked questions and the user's answers, keyed [Q1] to [Q3].

    A question that was skipped, expired or has no answer shows the skip line. No
    questions give an empty string.
    """
    if not records:
        return ""
    by_id = {answer.question_id: answer for answer in answers}
    lines = [_HEADER, ""]
    for index, record in enumerate(records, start=1):
        answer = by_id.get(record.question_id)
        text = answer.answer if answer is not None and answer.status == "answered" else _SKIPPED
        lines.append(f"- [Q{index}] Question: {record.question}")
        lines.append(f"  Our hypothesis: {record.hypothesis}")
        lines.append(f"  Answer: {text}")
    return "\n".join(lines)


def answers_section(state: Mapping[str, object]) -> str:
    """The USER ANSWERS section of a council state; empty when the state has no answers."""
    answers = cast(list[UserAnswer], state.get("user_answers") or [])
    if not answers:
        return ""
    records = cast(list[QuestionRecord], state.get("pending_questions") or [])
    return render_user_answers(records, answers)


def answered_keys(records: list[QuestionRecord], answers: list[UserAnswer]) -> set[str]:
    """The keys (``Q1`` to ``Q3``) of the questions whose answer has status ``answered``."""
    answered = {a.question_id for a in answers if a.status == "answered"}
    return {
        f"Q{index}"
        for index, record in enumerate(records, start=1)
        if record.question_id in answered
    }
