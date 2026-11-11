from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from whitespace.schemas.question import QuestionRecord
from whitespace.schemas.research import RawFinding
from whitespace.store._sqlite_rows import _SCHEMA
from whitespace.store.base import PendingPause
from whitespace.store.sqlite_store import SqliteSessionStore

_KILL = {
    "title": "Thermal runaway lag",
    "description": "Sensors detect runaway too late",
    "reason": "Covered by existing gas-sensing patents",
    "domain": "batteries",
}


def _finding(
    *,
    found_at: datetime = datetime(2026, 11, 1, tzinfo=UTC),
    content: str = "A sensor array inside the cell group",
    source_url: str | None = "https://example.org/paper/1",
    source_name: str = "Journal of Power Sources",
) -> RawFinding:
    return RawFinding(
        title="Early gas detection",
        content=content,
        source_type="paper",
        source_url=source_url,
        source_name=source_name,
        query="thermal runaway detection",
        found_at=found_at,
    )


async def test_the_same_discards_saved_twice_for_one_run_are_stored_once(
    tmp_path: Path,
) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")

    await store.save_discards("run-1", "gap", [_KILL])
    await store.save_discards("run-1", "gap", [_KILL])

    assert len(await store.list_discards("gap")) == 1


async def test_the_same_discards_for_a_different_run_are_stored(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")

    await store.save_discards("run-1", "gap", [_KILL])
    await store.save_discards("run-2", "gap", [_KILL])

    assert len(await store.list_discards("gap")) == 2


async def test_the_same_findings_saved_twice_for_one_run_are_stored_once(
    tmp_path: Path,
) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    finding = _finding()

    await store.save_raw_findings("run-1", [finding])
    await store.save_raw_findings("run-1", [finding])

    assert len(await store.list_raw_findings("run-1")) == 1


async def test_a_refetched_finding_with_new_time_and_text_is_stored_once(
    tmp_path: Path,
) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    first = _finding()
    refetched = _finding(
        found_at=datetime(2026, 11, 2, tzinfo=UTC), content="Updated abstract text"
    )

    await store.save_raw_findings("run-1", [first])
    await store.save_raw_findings("run-1", [refetched])

    stored = await store.list_raw_findings("run-1")
    assert [f.content for f in stored] == ["A sensor array inside the cell group"]


async def test_a_finding_with_no_link_is_matched_by_its_source_name(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    same_source = _finding(source_url=None, source_name="US1234567B2")
    other_source = _finding(source_url=None, source_name="US7654321B2")

    await store.save_raw_findings("run-1", [same_source, same_source, other_source])

    assert len(await store.list_raw_findings("run-1")) == 2


async def test_the_same_findings_for_a_different_run_are_stored(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")

    await store.save_raw_findings("run-1", [_finding()])
    await store.save_raw_findings("run-2", [_finding()])

    assert len(await store.list_raw_findings()) == 2


def _pause(**overrides: object) -> PendingPause:
    created = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    record = QuestionRecord(
        question_id="q1",
        run_id="job-1",
        stage="gap",
        purpose="clarify",
        question="Which operating temperature is required?",
        hypothesis="Below 80 C",
        rationale="This decides which materials remain viable.",
        asker_role="gap_identifier_1",
        asked=True,
        created_at=created,
    )
    fields: dict[str, object] = {
        "pause_id": "pause-1",
        "job_id": "job-1",
        "thread_id": "job-1",
        "stage": "gap",
        "questions": [record],
        "created_at": created,
    }
    fields.update(overrides)
    return PendingPause.model_validate(fields)


async def test_a_computed_pause_keeps_its_flag_through_save_and_get(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")

    await store.save_pending_pause(_pause(computed=True))

    loaded = await store.get_pending_pause()
    assert loaded is not None
    assert loaded.computed is True


async def test_a_pause_row_written_without_the_flag_loads_as_not_computed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "s.db"
    legacy = json.loads(_pause().model_dump_json())
    legacy.pop("computed", None)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.execute(
            "INSERT INTO pending_pauses (pause_id, created_at, pause_json) VALUES (?, ?, ?)",
            ("pause-1", legacy["created_at"], json.dumps(legacy)),
        )
        await db.commit()

    loaded = await SqliteSessionStore(db_path).get_pending_pause()

    assert loaded is not None
    assert loaded.computed is False
