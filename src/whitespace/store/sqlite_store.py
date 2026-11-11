from __future__ import annotations

import json
import logging
from pathlib import Path

import aiosqlite

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.store._sqlite_questions import SqliteQuestionStoreMixin
from whitespace.store._sqlite_research_rows import SqliteResearchRowsMixin
from whitespace.store._sqlite_rows import (
    _SCHEMA,
    ensure_domain_columns,
    row_to_gap_run,
    row_to_idea_run,
)
from whitespace.store.base import GapRun, IdeaRun, SessionStore

logger = logging.getLogger(__name__)


class SqliteSessionStore(SqliteResearchRowsMixin, SqliteQuestionStoreMixin, SessionStore):
    """SQLite-backed session store for BYOK mode."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._initialised = False

    async def _ensure_schema(self) -> None:
        if self._initialised:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await ensure_domain_columns(db)
        self._initialised = True
        logger.info("SqliteSessionStore: schema ready at %s", self._db_path)

    async def save_gap_run(self, run: GapRun) -> None:
        await self._ensure_schema()
        needs_json = json.dumps([n.model_dump() for n in run.needs])
        domain = run.domain.strip().lower() if run.domain else None
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO gap_runs"
                " (run_id, timestamp, needs_json, domain) VALUES (?, ?, ?, ?)",
                (run.run_id, run.timestamp.isoformat(), needs_json, domain),
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
            cursor = await db.execute("SELECT * FROM gap_runs ORDER BY timestamp DESC")
            rows = await cursor.fetchall()
        return [row_to_gap_run(row) for row in rows]

    async def list_idea_runs(self, gap_run_id: str | None = None) -> list[IdeaRun]:
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
        return [row_to_idea_run(row) for row in rows]

    async def get_gap_run(self, run_id: str) -> GapRun | None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM gap_runs WHERE run_id = ?", (run_id,))
            row = await cursor.fetchone()
        return row_to_gap_run(row) if row is not None else None

    async def get_idea_run(self, run_id: str) -> IdeaRun | None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM idea_runs WHERE run_id = ?", (run_id,))
            row = await cursor.fetchone()
        return row_to_idea_run(row) if row is not None else None

    async def get_all_previous_needs(self) -> list[UnmetNeed]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT needs_json FROM gap_runs")
            rows = await cursor.fetchall()
        return [UnmetNeed.model_validate(n) for row in rows for n in json.loads(row[0])]

    async def get_all_previous_proposals(self) -> list[IdeationProposal]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT proposals_json FROM idea_runs")
            rows = await cursor.fetchall()
        return [IdeationProposal.model_validate(p) for row in rows for p in json.loads(row[0])]
