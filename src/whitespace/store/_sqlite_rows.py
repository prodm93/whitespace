"""SQLite schema and row converters for the session store."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import aiosqlite

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.store.base import GapRun, IdeaRun

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

CREATE TABLE IF NOT EXISTS discards (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
    kind TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT NOT NULL, reason TEXT NOT NULL
);
"""


def row_to_gap_run(row: aiosqlite.Row) -> GapRun:
    needs = [UnmetNeed.model_validate(n) for n in json.loads(row["needs_json"])]
    return GapRun(
        run_id=row["run_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=UTC),
        needs=needs,
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
