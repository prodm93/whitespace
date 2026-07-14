"""SQLite schema, migration helpers, and row converters for the session store."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.store.base import GapRun, IdeaRun

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gap_runs (
    run_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, needs_json TEXT NOT NULL,
    domain TEXT
);

CREATE TABLE IF NOT EXISTS idea_runs (
    run_id TEXT PRIMARY KEY, gap_run_id TEXT NOT NULL,
    selected_need_titles_json TEXT NOT NULL, timestamp TEXT NOT NULL,
    proposals_json TEXT NOT NULL,
    FOREIGN KEY (gap_run_id) REFERENCES gap_runs(run_id)
);

CREATE TABLE IF NOT EXISTS raw_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
    found_at TEXT NOT NULL, finding_json TEXT NOT NULL, domain TEXT
);

CREATE TABLE IF NOT EXISTS discards (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
    kind TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT NOT NULL, reason TEXT NOT NULL, domain TEXT
);
"""

_DOMAIN_COLUMNS: dict[str, str] = {
    "gap_runs": "domain TEXT",
    "raw_findings": "domain TEXT",
    "discards": "domain TEXT",
}


async def ensure_domain_columns(db: aiosqlite.Connection) -> None:
    """Add domain column to tables that predate this migration."""
    for table, column_def in _DOMAIN_COLUMNS.items():
        cursor = await db.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in await cursor.fetchall()}
        if "domain" not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    await db.commit()


def _where(conditions: list[tuple[str, Any]]) -> tuple[str, tuple[Any, ...]]:
    """Build a WHERE clause from (predicate, value) pairs."""
    if not conditions:
        return "", ()
    return " WHERE " + " AND ".join(pred for pred, _ in conditions), tuple(v for _, v in conditions)


def row_to_gap_run(row: aiosqlite.Row) -> GapRun:
    needs = [UnmetNeed.model_validate(n) for n in json.loads(row["needs_json"])]
    return GapRun(
        run_id=row["run_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=UTC),
        needs=needs,
        domain=row["domain"],
    )


def row_to_idea_run(row: aiosqlite.Row) -> IdeaRun:
    proposals = [IdeationProposal.model_validate(p) for p in json.loads(row["proposals_json"])]
    titles = json.loads(row["selected_need_titles_json"])
    return IdeaRun(
        run_id=row["run_id"],
        gap_run_id=row["gap_run_id"],
        selected_need_titles=titles,
        timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=UTC),
        proposals=proposals,
    )
