"""A gap analysis stores its run and its final discards through the pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from whitespace.orchestration.pipeline import Pipeline
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.store.sqlite_store import SqliteSessionStore


def _need(title: str) -> UnmetNeed:
    return UnmetNeed(title=title, description="d", current_state="s", why_unmet="w")


def _discard(title: str) -> dict[str, str]:
    return {"title": title, "description": "d", "reason": "Covered by US1", "domain": "energy"}


def _pipeline(store: Any, result: tuple[list[UnmetNeed], list[dict[str, str]]]) -> Pipeline:
    gap_council = MagicMock()
    gap_council.run = AsyncMock(return_value=result)
    return Pipeline(
        config=MagicMock(),
        neo4j=MagicMock(),
        graphiti=MagicMock(),
        context_agent=MagicMock(),
        profile_agent=MagicMock(),
        ingest_graph=MagicMock(),
        gap_council=gap_council,
        ideation_council=MagicMock(),
        query_graph=MagicMock(),
        router=MagicMock(),
        dedup=MagicMock(),
        session_store=store,
    )


async def test_needs_and_discards_are_stored_once(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    needs = [_need("Heat recovery"), _need("Kiln sealing")]
    pipeline = _pipeline(store, (needs, [_discard("Kill A"), _discard("Kill B")]))

    result = await pipeline.analyse_gaps(
        ProfessionalProfile(), "Energy", run_id="run-1", fresh_start=True
    )

    assert result == needs
    stored = await store.get_gap_run("run-1")
    assert stored is not None
    assert [n.title for n in stored.needs] == ["Heat recovery", "Kiln sealing"]
    assert sorted(d["title"] for d in await store.list_discards("gap")) == ["Kill A", "Kill B"]


async def test_rejections_are_stored_when_no_need_survives(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    pipeline = _pipeline(store, ([], [_discard("Kill A")]))

    result = await pipeline.analyse_gaps(
        ProfessionalProfile(), "Energy", run_id="run-1", fresh_start=True
    )

    assert result == []
    assert [d["title"] for d in await store.list_discards("gap")] == ["Kill A"]
    assert await store.get_gap_run("run-1") is None


class _FailingDiscardStore(SqliteSessionStore):
    async def save_discards(self, run_id: str, kind: str, items: list[dict[str, str]]) -> None:
        raise OSError("disk full")


async def test_a_failed_discard_save_raises_and_stores_no_run(tmp_path: Path) -> None:
    store = _FailingDiscardStore(tmp_path / "s.db")
    pipeline = _pipeline(store, ([_need("Heat recovery")], [_discard("Kill A")]))

    with pytest.raises(OSError, match="disk full"):
        await pipeline.analyse_gaps(
            ProfessionalProfile(), "Energy", run_id="run-1", fresh_start=True
        )

    assert await store.get_gap_run("run-1") is None
