"""Ideator-driven novelty checking.

Each ideator hunts duplicates of its own ideas: it crafts queries
hellbent on finding identical or near-identical prior work, the
prior-art agent executes them, and the ideator decides per idea —
clear, modify, or drop. Two rounds maximum; whatever still has an
identifiable (semi-)duplicate after that is discarded automatically.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from whitespace.agents.council.prior_art_agent import PriorArtAgent
from whitespace.models.router import ModelRouter
from whitespace.schemas.idea import CandidateIdea

logger = logging.getLogger(__name__)

MAX_NOVELTY_ROUNDS = 2
_QUERIES_PER_IDEA = 2
_RESULTS_PER_QUERY = 5

_QUERY_PROMPT = """\
You are checking your own invention ideas for novelty. For each idea \
below, write {n} search queries hellbent on finding anything identical \
or nearly identical — the same problem solved the same way. Use the \
vocabulary a patent examiner or rival inventor would use, not your own \
phrasing. Return JSON: {{"queries": ["...", ...]}}.\
"""

_DECIDE_PROMPT = """\
You are judging whether your own invention ideas survive a novelty \
check. For each idea you will see search results from patents, papers \
and the web. Decide per idea:

- **clear** — nothing identical or near-identical exists.
- **modify** — something close exists, but the idea can be reworked to \
be genuinely distinct. Provide revised_title and revised_description \
that differentiate it concretely from what was found.
- **drop** — an identical or near-identical thing exists and no honest \
modification escapes it.

Be ruthless: a (semi-)duplicate that ships embarrasses everyone. \
Reference candidates by candidate_id.\
"""

_DECIDE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "NoveltyDecisions",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidate_id": {"type": "string"},
                            "action": {"type": "string", "enum": ["clear", "modify", "drop"]},
                            "revised_title": {"type": ["string", "null"]},
                            "revised_description": {"type": ["string", "null"]},
                        },
                        "required": [
                            "candidate_id",
                            "action",
                            "revised_title",
                            "revised_description",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["decisions"],
            "additionalProperties": False,
        },
    },
}


async def run_novelty_filter(
    router: ModelRouter,
    role: str,
    own: list[CandidateIdea],
    prior_art: PriorArtAgent,
) -> tuple[list[CandidateIdea], list[CandidateIdea]]:
    """Return (survivors, dropped) from the ideator's own novelty hunt.

    Dropped ideas are returned so the caller can persist them; a rerun
    must never resurrect an idea discarded for having prior art."""
    survivors: list[CandidateIdea] = []
    all_dropped: list[CandidateIdea] = []
    pending = list(own)
    for round_no in range(1, MAX_NOVELTY_ROUNDS + 1):
        if not pending:
            break
        queries = await _craft_queries(router, role, pending)
        findings = await prior_art.research(queries, per_query=_RESULTS_PER_QUERY)
        cleared, modified, dropped = await _decide(router, role, pending, findings)
        survivors.extend(cleared)
        if round_no == MAX_NOVELTY_ROUNDS and modified:
            dropped.extend(modified)
            modified = []
        if dropped:
            all_dropped.extend(dropped)
            logger.info(
                "novelty[%s] round %d: dropped %d (semi-)duplicates",
                role,
                round_no,
                len(dropped),
            )
        pending = modified
    return survivors, all_dropped


async def _craft_queries(
    router: ModelRouter,
    role: str,
    ideas: list[CandidateIdea],
) -> list[str]:
    listing = "\n\n".join(f"[{i.candidate_id}] **{i.title}**: {i.description}" for i in ideas)
    result = await router.call(
        role=role,
        messages=[
            {"role": "system", "content": _QUERY_PROMPT.format(n=_QUERIES_PER_IDEA)},
            {"role": "user", "content": listing},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    try:
        queries = json.loads(result["content"]).get("queries", [])
    except (json.JSONDecodeError, AttributeError):
        logger.warning("novelty[%s]: query crafting returned malformed JSON", role)
        return [i.title for i in ideas]
    return [q for q in queries if isinstance(q, str) and q.strip()]


async def _decide(
    router: ModelRouter,
    role: str,
    ideas: list[CandidateIdea],
    findings: list[Any],
) -> tuple[list[CandidateIdea], list[CandidateIdea], list[CandidateIdea]]:
    listing = "\n\n".join(f"[{i.candidate_id}] **{i.title}**: {i.description}" for i in ideas)
    evidence = (
        "\n".join(
            f"- [{f.source_type}] {f.title} ({f.published or 'n.d.'}): {f.content[:300]}"
            for f in findings
        )
        or "(no results found)"
    )
    result = await router.call(
        role=role,
        messages=[
            {"role": "system", "content": _DECIDE_PROMPT},
            {
                "role": "user",
                "content": f"## YOUR IDEAS\n\n{listing}\n\n## SEARCH RESULTS\n\n{evidence}",
            },
        ],
        temperature=0.0,
        response_format=_DECIDE_FORMAT,
    )
    decisions = {d["candidate_id"]: d for d in json.loads(result["content"]).get("decisions", [])}
    cleared: list[CandidateIdea] = []
    modified: list[CandidateIdea] = []
    dropped: list[CandidateIdea] = []
    for idea in ideas:
        decision = decisions.get(idea.candidate_id)
        if decision is None or decision["action"] == "clear":
            cleared.append(idea)
        elif decision["action"] == "modify":
            modified.append(
                idea.model_copy(
                    update={
                        "title": decision.get("revised_title") or idea.title,
                        "description": decision.get("revised_description") or idea.description,
                    }
                )
            )
        else:
            dropped.append(idea)
    return cleared, modified, dropped
