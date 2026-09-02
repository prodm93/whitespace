from __future__ import annotations

from typing import Any

import aiosqlite

from whitespace.schemas.question import QuestionRecord
from whitespace.store.base import PendingPause


class SqliteQuestionStoreMixin:
    _db_path: str

    async def _ensure_schema(self) -> None:
        raise NotImplementedError

    async def save_question_records(self, records: list[QuestionRecord]) -> None:
        if not records:
            return
        await self._ensure_schema()
        rows = [
            (record.question_id, record.created_at.isoformat(), record.model_dump_json())
            for record in records
        ]
        async with aiosqlite.connect(self._db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO questions"
                " (question_id, created_at, record_json) VALUES (?, ?, ?)",
                rows,
            )
            await db.commit()

    async def list_question_records(self, limit: int | None = None) -> list[QuestionRecord]:
        if limit is not None and limit <= 0:
            return []
        await self._ensure_schema()
        query = "SELECT record_json FROM questions ORDER BY created_at DESC"
        params: tuple[int, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [QuestionRecord.model_validate_json(row[0]) for row in rows]

    async def update_question_record(self, question_id: str, **fields: Any) -> None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT record_json FROM questions WHERE question_id = ?",
                (question_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return
            current = QuestionRecord.model_validate_json(row[0])
            updated = QuestionRecord.model_validate({**current.model_dump(), **fields})
            await db.execute(
                "UPDATE questions SET created_at = ?, record_json = ? WHERE question_id = ?",
                (updated.created_at.isoformat(), updated.model_dump_json(), question_id),
            )
            await db.commit()

    async def save_pending_pause(self, pause: PendingPause) -> None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO pending_pauses"
                " (pause_id, created_at, pause_json) VALUES (?, ?, ?)",
                (pause.pause_id, pause.created_at.isoformat(), pause.model_dump_json()),
            )
            await db.commit()

    async def get_pending_pause(self) -> PendingPause | None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT pause_json FROM pending_pauses ORDER BY created_at DESC LIMIT 1"
            )
            row = await cursor.fetchone()
        return PendingPause.model_validate_json(row[0]) if row is not None else None

    async def delete_pending_pause(self, pause_id: str) -> None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM pending_pauses WHERE pause_id = ?", (pause_id,))
            await db.commit()
