"""Scoring, capping and rendering for the neighbour memory bucket."""

from __future__ import annotations

import logging

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.research import RawFinding
from whitespace.tools.dedup import SemanticDeduplicator

logger = logging.getLogger(__name__)

_NEIGHBOUR_FLOOR = 0.85
_MAX_MEMORY_ITEMS = 40
_MAX_NEEDS = 15
_MAX_DISCARDS = 10
_MAX_FINDINGS = 15


def _apply_type_caps(
    sorted_by_type: list[list[tuple[float, str]]],
    type_caps: list[int],
) -> list[tuple[float, str]]:
    """Select up to type_caps[i] items from each bucket; backfill unused slots by score."""
    selected = [items[:cap] for items, cap in zip(sorted_by_type, type_caps, strict=True)]
    unused = sum(cap - len(sel) for cap, sel in zip(type_caps, selected, strict=True))
    remaining = sorted(
        [
            item
            for items, cap in zip(sorted_by_type, type_caps, strict=True)
            for item in items[cap:]
        ],
        key=lambda x: x[0],
        reverse=True,
    )[:unused]
    combined = [item for sel in selected for item in sel] + remaining
    return sorted(combined, key=lambda x: x[0], reverse=True)


async def _score_neighbours(
    domain: str,
    other_needs: list[tuple[str | None, UnmetNeed]],
    other_discards: list[dict[str, str]],
    other_findings: list[RawFinding],
    scorer: SemanticDeduplicator,
) -> list[tuple[float, str]]:
    """Score and cap other-domain items per type; return (score, rendered_line) pairs."""
    need_cands: list[tuple[str, str]] = [
        (
            f"{n.title}: {n.description}",
            f"- [from {s or 'unknown domain'}] {n.title}: {n.description[:300]}",
        )
        for s, n in other_needs
    ]
    discard_cands: list[tuple[str, str]] = [
        (
            f"{d['title']}: {d['description']}",
            f"- [from {d.get('domain') or 'unknown domain'};"
            f" previously rejected: {d['reason']}] {d['title']}: {d['description'][:300]}",
        )
        for d in other_discards
    ]
    finding_cands: list[tuple[str, str]] = [
        (
            f"{f.title}: {f.content}",
            f"- [from {f.domain or 'unknown domain'}, {f.found_at:%Y-%m-%d};"
            f" query: {f.query}] {f.title}: {f.content[:300]}",
        )
        for f in other_findings
    ]
    all_cands = need_cands + discard_cands + finding_cands
    if not all_cands:
        return []
    texts = [t for t, _ in all_cands]
    scores = await scorer.score_against(texts, [domain])
    if scores:
        med = sorted(scores)[len(scores) // 2]
        logger.info(
            "_score_neighbours: %d candidates, max %.2f, median %.2f, %d >= floor",
            len(scores),
            max(scores),
            med,
            sum(1 for s in scores if s >= _NEIGHBOUR_FLOOR),
        )
    n_n, n_d = len(need_cands), len(discard_cands)

    def _above(cands: list[tuple[str, str]], s: list[float]) -> list[tuple[float, str]]:
        return sorted(
            [(sc, r) for sc, (_, r) in zip(s, cands, strict=True) if sc >= _NEIGHBOUR_FLOOR],
            key=lambda x: x[0],
            reverse=True,
        )

    return _apply_type_caps(
        [
            _above(need_cands, scores[:n_n]),
            _above(discard_cands, scores[n_n : n_n + n_d]),
            _above(finding_cands, scores[n_n + n_d :]),
        ],
        [_MAX_NEEDS, _MAX_DISCARDS, _MAX_FINDINGS],
    )


def _render_neighbours(items: list[tuple[float, str]]) -> str:
    if not items:
        return ""
    return "\n".join(f"{rendered} (similarity {score:.2f})" for score, rendered in items)
