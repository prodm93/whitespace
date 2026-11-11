"""Raw research findings and discarded candidates in the SQLite session store."""

from __future__ import annotations

import logging

import aiosqlite

from whitespace.schemas.research import RawFinding
from whitespace.store._sqlite_rows import _where

logger = logging.getLogger(__name__)


def finding_identity(finding: RawFinding) -> tuple[str, str, str]:
    """Source type, link (or source name when there is no link) and query.

    The retrieval time and the text are not part of it, so a repeated search
    that returns the same result matches the stored finding.
    """
    return (finding.source_type, finding.source_url or finding.source_name, finding.query)


def _discard_key(item: dict[str, str]) -> tuple[str, str, str]:
    return (item.get("title", ""), item.get("description", ""), item.get("reason", ""))


class SqliteResearchRowsMixin:
    _db_path: str

    async def _ensure_schema(self) -> None:
        raise NotImplementedError

    async def save_raw_findings(self, run_id: str, findings: list[RawFinding]) -> None:
        """Store findings; one whose identity is already stored for this run is skipped.

        Two findings with the same identity in one call are stored once.
        """
        if not findings:
            return
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT finding_json FROM raw_findings WHERE run_id = ?", (run_id,)
            )
            seen = {
                finding_identity(RawFinding.model_validate_json(row[0]))
                for row in await cursor.fetchall()
            }
            rows = []
            for f in findings:
                identity = finding_identity(f)
                if identity in seen:
                    continue
                seen.add(identity)
                rows.append(
                    (
                        run_id,
                        f.found_at.isoformat(),
                        f.model_dump_json(),
                        f.domain.strip().lower() if f.domain else None,
                    )
                )
            await db.executemany(
                "INSERT INTO raw_findings (run_id, found_at, finding_json, domain)"
                " VALUES (?, ?, ?, ?)",
                rows,
            )
            await db.commit()
        logger.info("SqliteSessionStore: saved %d raw findings for run %s", len(rows), run_id)

    async def list_raw_findings(self, run_id: str | None = None) -> list[RawFinding]:
        await self._ensure_schema()
        conds = []
        if run_id is not None:
            conds.append(("run_id = ?", run_id))
        where, params = _where(conds)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"SELECT finding_json FROM raw_findings{where} ORDER BY found_at DESC", params
            )
            rows = await cursor.fetchall()
        return [RawFinding.model_validate_json(row[0]) for row in rows]

    async def save_discards(self, run_id: str, kind: str, items: list[dict[str, str]]) -> None:
        """Store discards; an item already stored for this run is skipped.

        An item is already stored when a row has the same run, kind, title,
        description and reason.
        """
        if not items:
            return
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT title, description, reason FROM discards WHERE run_id = ? AND kind = ?",
                (run_id, kind),
            )
            stored = {tuple(row) for row in await cursor.fetchall()}
            rows = [
                (
                    run_id,
                    kind,
                    i.get("title", ""),
                    i.get("description", ""),
                    i.get("reason", ""),
                    i.get("domain", "").strip().lower() or None,
                )
                for i in items
                if _discard_key(i) not in stored
            ]
            await db.executemany(
                "INSERT INTO discards (run_id, kind, title, description, reason, domain)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            await db.commit()
        logger.info("SqliteSessionStore: saved %d %s discards", len(rows), kind)

    async def list_discards(self, kind: str | None = None) -> list[dict[str, str]]:
        await self._ensure_schema()
        conds = []
        if kind is not None:
            conds.append(("kind = ?", kind))
        where, params = _where(conds)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT kind, title, description, reason, domain FROM discards{where}"
                " ORDER BY id DESC",
                params,
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]
