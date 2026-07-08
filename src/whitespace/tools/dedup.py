"""Semantic deduplication of research findings.

Crude by design: embed each finding once, drop any finding whose cosine
similarity to an already-kept finding exceeds the threshold. Embedding
comparison costs near nothing next to the pipeline's LLM spend, and the
expensive judgment stays with the council critics.
"""

from __future__ import annotations

import logging
import math

from whitespace.graph.graphiti_client import GraphitiClient
from whitespace.schemas.research import RawFinding

logger = logging.getLogger(__name__)

_SIMILARITY_THRESHOLD = 0.90
_EMBED_CHARS = 512


class SemanticDeduplicator:
    """Drops near-duplicate findings using the Graphiti embedder."""

    def __init__(self, graphiti: GraphitiClient, threshold: float = _SIMILARITY_THRESHOLD) -> None:
        self._graphiti = graphiti
        self._threshold = threshold

    async def dedup(self, findings: list[RawFinding]) -> list[RawFinding]:
        if len(findings) < 2:
            return findings

        unique, texts = _drop_exact(findings)
        embedder = self._graphiti.graphiti.embedder
        try:
            vectors = await embedder.create_batch(texts)
        except Exception:
            logger.exception("SemanticDeduplicator: embedding failed; keeping all findings")
            return unique

        kept: list[RawFinding] = []
        kept_vectors: list[list[float]] = []
        for finding, vector in zip(unique, vectors, strict=True):
            if any(_cosine(vector, kv) >= self._threshold for kv in kept_vectors):
                continue
            kept.append(finding)
            kept_vectors.append(vector)
        logger.info(
            "SemanticDeduplicator: %d findings -> %d after dedup",
            len(findings),
            len(kept),
        )
        return kept


def _drop_exact(findings: list[RawFinding]) -> tuple[list[RawFinding], list[str]]:
    """Cheap first pass: drop byte-identical texts before embedding."""
    unique: list[RawFinding] = []
    texts: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        text = f"{finding.title}\n{finding.content}"[:_EMBED_CHARS]
        if text in seen:
            continue
        seen.add(text)
        unique.append(finding)
        texts.append(text)
    return unique, texts


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
