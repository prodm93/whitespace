"""Tests for SemanticDeduplicator.score_against and score_against_with_best."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from whitespace.tools.dedup import SemanticDeduplicator, _cosine


def _dedup(vectors: list[list[float]]) -> SemanticDeduplicator:
    """Fake embedder that returns the given vectors in call order."""
    embedder = MagicMock()
    embedder.create_batch = AsyncMock(return_value=vectors)
    graphiti = MagicMock()
    graphiti.graphiti.embedder = embedder
    return SemanticDeduplicator(graphiti)


def _dedup_failing() -> SemanticDeduplicator:
    """Fake embedder whose create_batch always raises."""
    embedder = MagicMock()
    embedder.create_batch = AsyncMock(side_effect=RuntimeError("embed error"))
    graphiti = MagicMock()
    graphiti.graphiti.embedder = embedder
    return SemanticDeduplicator(graphiti)


# ---------------------------------------------------------------------------
# score_against
# ---------------------------------------------------------------------------


class TestScoreAgainst:
    def test_returns_max_cosine_per_text(self) -> None:
        # texts: [1,0], [0,1]  reference: [1,0], [0,1]
        # text[0] max cosine = max(cos([1,0],[1,0]), cos([1,0],[0,1])) = 1.0
        # text[1] max cosine = max(cos([0,1],[1,0]), cos([0,1],[0,1])) = 1.0
        dedup = _dedup([[1, 0], [0, 1], [1, 0], [0, 1]])
        result = asyncio.run(dedup.score_against(["a", "b"], ["r1", "r2"]))
        assert len(result) == 2
        assert abs(result[0] - 1.0) < 1e-9
        assert abs(result[1] - 1.0) < 1e-9

    def test_picks_best_reference(self) -> None:
        # text: [1,0]  references: [1,0] and [0,1]
        # max cosine = 1.0 (matches first reference exactly)
        dedup = _dedup([[1, 0], [1, 0], [0, 1]])
        result = asyncio.run(dedup.score_against(["t"], ["r_exact", "r_orthogonal"]))
        assert abs(result[0] - 1.0) < 1e-9

    def test_orthogonal_gives_zero(self) -> None:
        dedup = _dedup([[1, 0, 0], [0, 1, 0]])
        result = asyncio.run(dedup.score_against(["t"], ["r"]))
        assert abs(result[0]) < 1e-9

    def test_fail_open_on_embedding_error(self) -> None:
        dedup = _dedup_failing()
        result = asyncio.run(dedup.score_against(["a", "b", "c"], ["r"]))
        assert result == [0.0, 0.0, 0.0]

    def test_empty_texts_returns_empty(self) -> None:
        dedup = _dedup([])
        result = asyncio.run(dedup.score_against([], ["r"]))
        assert result == []

    def test_empty_reference_returns_zeros(self) -> None:
        dedup = _dedup([])
        result = asyncio.run(dedup.score_against(["t"], []))
        assert result == [0.0]


# ---------------------------------------------------------------------------
# score_against_with_best
# ---------------------------------------------------------------------------


class TestScoreAgainstWithBest:
    def test_returns_score_and_best_matching_text(self) -> None:
        # text: [1,0]  references: [0,1] (low sim), [1,0] (exact match)
        # batch order: text, ref_a, ref_b → [1,0], [0,1], [1,0]
        dedup = _dedup([[1, 0], [0, 1], [1, 0]])
        result = asyncio.run(dedup.score_against_with_best(["t"], ["ref_low", "ref_exact"]))
        score, best = result[0]
        assert abs(score - 1.0) < 1e-9
        assert best == "ref_exact"

    def test_fail_open_on_embedding_error(self) -> None:
        dedup = _dedup_failing()
        result = asyncio.run(dedup.score_against_with_best(["a", "b"], ["r"]))
        assert result == [(0.0, ""), (0.0, "")]

    def test_empty_texts_returns_empty(self) -> None:
        dedup = _dedup([])
        result = asyncio.run(dedup.score_against_with_best([], ["r"]))
        assert result == []

    def test_empty_reference_returns_zeros(self) -> None:
        dedup = _dedup([])
        result = asyncio.run(dedup.score_against_with_best(["t"], []))
        assert result == [(0.0, "")]


# ---------------------------------------------------------------------------
# _cosine helper
# ---------------------------------------------------------------------------


class TestCosine:
    def test_identical_vectors(self) -> None:
        assert abs(_cosine([1, 0], [1, 0]) - 1.0) < 1e-9

    def test_orthogonal_vectors(self) -> None:
        assert abs(_cosine([1, 0], [0, 1])) < 1e-9

    def test_zero_vector(self) -> None:
        assert _cosine([0, 0], [1, 0]) == 0.0
