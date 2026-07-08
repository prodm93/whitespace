from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.research import RawFinding
from whitespace.store.base import GapRun, IdeaRun, SessionStore

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gap_runs (
    run_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, needs_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idea_runs (
    run_id TEXT PRIMARY KEY, gap_run_id TEXT NOT NULL,
    selected_need_titles_json TEXT NOT NULL, timestamp TEXT NOT NULL,
    proposals_json TEXT NOT NULL,
    FOREIGN KEY (gap_run_id) REFERENCES gap_runs(run_id)
);

CREATE TABLE IF NOT EXISTS raw_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
    found_at TEXT NOT NULL, finding_json TEXT NOT NULL
);
"""


class SqliteSessionStore(SessionStore):
    """SQLite-backed session store for BYOK mode."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._initialised = False

    async def _ensure_schema(self) -> None:
        if self._initialised:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        self._initialised = True
        logger.info("SqliteSessionStore: schema ready at %s", self._db_path)

    async def save_gap_run(self, run: GapRun) -> None:
        await self._ensure_schema()
        needs_json = json.dumps([n.model_dump() for n in run.needs])
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO gap_runs (run_id, timestamp, needs_json) VALUES (?, ?, ?)",
                (run.run_id, run.timestamp.isoformat(), needs_json),
            )
            await db.commit()

    async def save_idea_run(self, run: IdeaRun) -> None:
        await self._ensure_schema()
        proposals_json = json.dumps([p.model_dump() for p in run.proposals])
        titles_json = json.dumps(run.selected_need_titles)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO idea_runs "
                "(run_id, gap_run_id, selected_need_titles_json, timestamp, proposals_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    run.run_id,
                    run.gap_run_id,
                    titles_json,
                    run.timestamp.isoformat(),
                    proposals_json,
                ),
            )
            await db.commit()

    async def list_gap_runs(self) -> list[GapRun]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT run_id, timestamp, needs_json FROM gap_runs ORDER BY timestamp DESC"
            )
            rows = await cursor.fetchall()
        return [_row_to_gap_run(row) for row in rows]

    async def list_idea_runs(
        self,
        gap_run_id: str | None = None,
    ) -> list[IdeaRun]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if gap_run_id is not None:
                cursor = await db.execute(
                    "SELECT * FROM idea_runs WHERE gap_run_id = ? ORDER BY timestamp DESC",
                    (gap_run_id,),
                )
            else:
                cursor = await db.execute("SELECT * FROM idea_runs ORDER BY timestamp DESC")
            rows = await cursor.fetchall()
        return [_row_to_idea_run(row) for row in rows]

    async def get_gap_run(self, run_id: str) -> GapRun | None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT run_id, timestamp, needs_json FROM gap_runs WHERE run_id = ?",
                (run_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_gap_run(row)

    async def get_idea_run(self, run_id: str) -> IdeaRun | None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM idea_runs WHERE run_id = ?",
                (run_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_idea_run(row)

    async def get_all_previous_needs(self) -> list[UnmetNeed]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT needs_json FROM gap_runs")
            rows = await cursor.fetchall()
        all_needs: list[UnmetNeed] = []
        for row in rows:
            raw = json.loads(row[0])
            all_needs.extend(UnmetNeed.model_validate(n) for n in raw)
        return all_needs

    async def get_all_previous_proposals(self) -> list[IdeationProposal]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT proposals_json FROM idea_runs")
            rows = await cursor.fetchall()
        all_proposals: list[IdeationProposal] = []
        for row in rows:
            raw = json.loads(row[0])
            all_proposals.extend(IdeationProposal.model_validate(p) for p in raw)
        return all_proposals

    async def save_raw_findings(self, run_id: str, findings: list[RawFinding]) -> None:
        if not findings:
            return
        await self._ensure_schema()
        rows = [(run_id, f.found_at.isoformat(), f.model_dump_json()) for f in findings]
        async with aiosqlite.connect(self._db_path) as db:
            await db.executemany(
                "INSERT INTO raw_findings (run_id, found_at, finding_json) VALUES (?, ?, ?)",
                rows,
            )
            await db.commit()
        logger.info("SqliteSessionStore: saved %d raw findings for run %s", len(rows), run_id)

    async def list_raw_findings(self, run_id: str | None = None) -> list[RawFinding]:
        await self._ensure_schema()
        where = " WHERE run_id = ?" if run_id is not None else ""
        params = (run_id,) if run_id is not None else ()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"SELECT finding_json FROM raw_findings{where} ORDER BY found_at DESC", params
            )
            rows = await cursor.fetchall()
        return [RawFinding.model_validate_json(row[0]) for row in rows]


def _row_to_gap_run(row: aiosqlite.Row) -> GapRun:
    needs = [UnmetNeed.model_validate(n) for n in json.loads(row["needs_json"])]
    return GapRun(
        run_id=row["run_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=UTC),
        needs=needs,
    )


def _row_to_idea_run(row: aiosqlite.Row) -> IdeaRun:
    proposals = [IdeationProposal.model_validate(p) for p in json.loads(row["proposals_json"])]
    titles = json.loads(row["selected_need_titles_json"])
    return IdeaRun(
        run_id=row["run_id"],
        gap_run_id=row["gap_run_id"],
        selected_need_titles=titles,
        timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=UTC),
        proposals=proposals,
    )
