"""Extractive rendering of tool-loop exploration transcripts for council prompts."""

from __future__ import annotations

import asyncio
import logging
import re

from whitespace.schemas.critique import CandidateLike
from whitespace.tools.dedup import SemanticDeduplicator

logger = logging.getLogger(__name__)

# Per-trail budget; each identifier's exploration is capped before assembly.
_TRAIL_BUDGET_CHARS = 4000  # REVISIT: tune if results suggest
_MIN_TRAIL_CHUNKS = 2  # REVISIT: tune if results suggest
# References are split into multiple entries because the embed window clips
# each string to its first 512 chars; one long flattened string would push
# graph-citation text past the clip boundary.
_EMBED_CHARS = 512


def _parse_trail(transcript: str) -> tuple[list[str], str]:
    """Split a tool-loop transcript into (tool_call_chunks, closing_summary).

    Tool chunks start with '### '; the closing summary is any non-tool text.
    Returns an empty summary string when the model hit its cap without
    producing a concluding statement.
    """
    if not transcript or transcript.startswith("("):
        return [], transcript
    parts = re.split(r"\n\n(?=### )", transcript)
    tool_chunks: list[str] = []
    summary = ""
    for part in parts:
        if part.startswith("### "):
            tool_chunks.append(part)
        else:
            summary = part

    # When all parts are tool chunks, the closing summary may be appended
    # to the last one after the final \n\n (no ### follows it, so the
    # lookahead regex did not split there).
    if tool_chunks and not summary:
        last = tool_chunks[-1]
        idx = last.rfind("\n\n")
        if idx != -1:
            tail = last[idx + 2 :]
            if tail and not tail.startswith("### "):
                summary = tail
                tool_chunks[-1] = last[:idx]

    return [c for c in tool_chunks if c], summary


def build_gap_references(candidates: list[CandidateLike]) -> list[str]:
    """Build a multi-entry reference list for trail relevance scoring.

    Each candidate contributes title+description as one entry, plus each
    'graph:' citation as a separate entry, so that neither is clipped out
    of the embed window by a longer flattened string.
    """
    refs: list[str] = []
    for c in candidates:
        refs.append(f"{c.title}: {c.description}")
        for ev in getattr(c, "evidence", []):
            if isinstance(ev, str) and ev.startswith("graph:"):
                refs.append(ev[len("graph:") :].strip())
    return refs


async def render_trail(
    transcript: str,
    references: list[str],
    scorer: SemanticDeduplicator,
    *,
    budget: int = _TRAIL_BUDGET_CHARS,
    min_chunks: int = _MIN_TRAIL_CHUNKS,
) -> str:
    """Render an exploration transcript extractively within the per-trail budget.

    The closing summary is always kept. Remaining tool-call chunks are
    admitted by descending relevance score until the budget is spent; the
    minimum-chunks floor is honoured regardless of score. Elided chunks are
    replaced with an honest marker so the reader knows evidence was withheld,
    not absent. Degrades to first-N on scoring failure.
    """
    tool_chunks, summary = _parse_trail(transcript)
    if not tool_chunks:
        return transcript[:budget]

    summary_chars = len(summary) + (4 if summary else 0)
    chunk_budget = max(0, budget - summary_chars)

    if not references:
        selected = _first_n_in_budget(tool_chunks, chunk_budget, min_chunks)
        return _assemble_list(selected, summary, len(tool_chunks))

    try:
        scores = await scorer.score_against(tool_chunks, references)
    except Exception:
        logger.warning("render_trail: scoring failed; falling back to first-N")
        selected = _first_n_in_budget(tool_chunks, chunk_budget, min_chunks)
        return _assemble_list(selected, summary, len(tool_chunks))

    selected_idx = _select_by_score(tool_chunks, scores, chunk_budget, min_chunks)
    return _assemble_indexed(tool_chunks, selected_idx, summary)


async def build_exploration_context(
    roles: set[str],
    findings_by_role: dict[str, str],
    candidates_by_role: dict[str, list[CandidateLike]],
    scorer: SemanticDeduplicator,
) -> str:
    """Assemble per-role exploration transcripts, extractively rendered within budget.

    The critic passes all identifier roles; the synthesiser passes surviving
    roles only. Each role's references come from its own candidates (critic
    and revision) or from all surviving candidates mapped uniformly (synthesis).
    """
    role_order = sorted(r for r in roles if findings_by_role.get(r))
    if not role_order:
        return ""
    refs_by_role = {
        role: build_gap_references(candidates_by_role.get(role, [])) for role in role_order
    }
    rendered = await asyncio.gather(
        *[render_trail(findings_by_role[role], refs_by_role[role], scorer) for role in role_order]
    )
    return "".join(
        f"\n\n## Exploration by {role}\n{trail}"
        for role, trail in zip(role_order, rendered, strict=True)
        if trail
    )


def _first_n_in_budget(chunks: list[str], budget: int, min_n: int) -> list[str]:
    selected: list[str] = []
    used = 0
    for chunk in chunks:
        if used + len(chunk) <= budget or len(selected) < min_n:
            selected.append(chunk)
            used += len(chunk) + 4
    return selected


def _select_by_score(chunks: list[str], scores: list[float], budget: int, min_n: int) -> set[int]:
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    selected: set[int] = set()
    used = 0
    for i in ranked:
        chunk = chunks[i]
        if used + len(chunk) <= budget or len(selected) < min_n:
            selected.add(i)
            used += len(chunk) + 4
        if used >= budget and len(selected) >= min_n:
            break
    return selected


def _assemble_list(selected: list[str], summary: str, total_tool_count: int) -> str:
    elided = total_tool_count - len(selected)
    parts = list(selected)
    if elided:
        noun = "result" if elided == 1 else "results"
        parts.append(f"[... {elided} tool {noun} elided ...]")
    if summary:
        parts.append(summary)
    return "\n\n".join(parts)


def _assemble_indexed(chunks: list[str], selected_idx: set[int], summary: str) -> str:
    parts: list[str] = []
    elided = 0
    for i, chunk in enumerate(chunks):
        if i in selected_idx:
            if elided:
                noun = "result" if elided == 1 else "results"
                parts.append(f"[... {elided} tool {noun} elided ...]")
                elided = 0
            parts.append(chunk)
        else:
            elided += 1
    if elided:
        noun = "result" if elided == 1 else "results"
        parts.append(f"[... {elided} tool {noun} elided ...]")
    if summary:
        parts.append(summary)
    return "\n\n".join(parts)
