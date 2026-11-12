"""One refine call: a council member revises and extends its candidates from the answers."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from whitespace.agents.council._helpers import format_profile
from whitespace.models.router import ModelRouter
from whitespace.schemas.critique import CandidateLike
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)

C = TypeVar("C", bound=CandidateLike)

# REVISIT: tune if results suggest
MAX_FOLLOW_UP_QUERIES = 3
# REVISIT: tune if results suggest
MAX_NEW_CANDIDATES = 2


@dataclass
class RefineOutput:
    model_id: str
    items: list[dict[str, Any]]
    new_items: list[dict[str, Any]]
    follow_up_queries: list[str]


@dataclass
class Refined(Generic[C]):
    revised: list[C]
    added: list[C] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)


def _listing(own: Sequence[CandidateLike]) -> str:
    parts: list[str] = []
    for i, candidate in enumerate(own, 1):
        entry = f"{i}. **{candidate.title}**: {candidate.description}"
        evidence = getattr(candidate, "evidence", [])
        if evidence:
            entry += f"\n   evidence: {', '.join(evidence)}"
        parts.append(entry)
    return "\n\n".join(parts)


def _valid_queries(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [q for q in value if isinstance(q, str) and q.strip()]


def _cites_answer(item: dict[str, Any], valid_keys: set[str]) -> bool:
    """A new gap cites [Qn] or Qn in its evidence list; a new idea names [Qn] in its text."""
    if "evidence" in item:
        entries = [e.strip() for e in item.get("evidence") or [] if isinstance(e, str)]
        return any(e == key or f"[{key}]" in e for e in entries for key in valid_keys)
    description = str(item.get("description", ""))
    return any(f"[{key}]" in description for key in valid_keys)


def _new_items(value: Any, valid_keys: set[str], role: str) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for item in _item_list(value):
        if _cites_answer(item, valid_keys):
            kept.append(item)
        else:
            logger.info("%s: dropped a new candidate that cites no answered question", role)
    return kept[:MAX_NEW_CANDIDATES]


def _item_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


async def request_refinement(
    router: ModelRouter,
    *,
    role: str,
    system_prompt: str,
    response_format: dict[str, Any],
    response_key: str,
    new_key: str,
    own: Sequence[CandidateLike],
    answers_text: str,
    context: str,
    profile: ProfessionalProfile,
    allow_queries: bool,
    valid_keys: set[str],
) -> RefineOutput:
    """Ask the member to refine its own candidates in the light of the user's answers."""
    user_msg = (
        f"## YOUR CANDIDATES\n\n{_listing(own)}\n\n{answers_text}\n\n"
        f"## EVIDENCE\n\n{context}\n\n## USER PROFILE\n\n{format_profile(profile)}"
    )
    result = await router.call(
        role=role,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        response_format=response_format,
    )
    parsed = json.loads(result["content"])
    queries = parsed.get("follow_up_queries") if allow_queries else []
    return RefineOutput(
        model_id=result["model_id"],
        items=_item_list(parsed.get(response_key)),
        new_items=_new_items(parsed.get(new_key), valid_keys, role),
        follow_up_queries=_valid_queries(queries)[:MAX_FOLLOW_UP_QUERIES],
    )
