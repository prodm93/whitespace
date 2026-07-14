"""Tests for domain-aware store operations: migration and round-trips."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.research import RawFinding
from whitespace.store._sqlite_rows import _SCHEMA, ensure_domain_columns
from whitespace.store.base import GapRun
from whitespace.store.sqlite_store import SqliteSessionStore

_TS = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)

_NEED = UnmetNeed(
    title="Thermal runaway lag",
    description="Existing sensors detect thermal runaway too late",
    current_state="Voltage-drop detection triggers after propagation begins",
    why_unmet="No cost-effective early-stage gas sensing",
    matching_skills=["battery management"],
)

_FINDING = RawFinding(
    title="Early gas detection",
    content="A sensor array positioned within the cell group",
    source_type="paper",
    source_name="Journal of Power Sources",
    query="thermal runaway detection",
    found_at=_TS,
    domain="lithium-ion batteries",
)


def _run(domain: str | None = "lithium-ion batteries") -> GapRun:
    return GapRun(run_id="r1", timestamp=_TS, needs=[_NEED], domain=domain)


def _store(path: Path) -> SqliteSessionStore:
    return SqliteSessionStore(path)


# ---------------------------------------------------------------------------
# SQLite migration
# ---------------------------------------------------------------------------


class TestSqliteMigration:
    def test_new_database_has_domain_columns(self, tmp_path: Path) -> None:
        db_path = tmp_path / "new.db"

        async def run() -> None:
            async with aiosqlite.connect(db_path) as db:
                await db.executescript(_SCHEMA)
                await ensure_domain_columns(db)
                for table in ("gap_runs", "raw_findings", "discards"):
                    cursor = await db.execute(f"PRAGMA table_info({table})")
                    cols = {row[1] for row in await cursor.fetchall()}
                    assert "domain" in cols, f"{table} missing domain column"

        asyncio.run(run())

    def test_legacy_database_gets_domain_column_added(self, tmp_path: Path) -> None:
        db_path = tmp_path / "legacy.db"
        old_schema = """
        CREATE TABLE IF NOT EXISTS gap_runs (
            run_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, needs_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS raw_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            found_at TEXT NOT NULL, finding_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS discards (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            kind TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
            reason TEXT NOT NULL
        );
        """

        async def run() -> None:
            async with aiosqlite.connect(db_path) as db:
                await db.executescript(old_schema)
                await db.commit()
            async with aiosqlite.connect(db_path) as db:
                await ensure_domain_columns(db)
                for table in ("gap_runs", "raw_findings", "discards"):
                    cursor = await db.execute(f"PRAGMA table_info({table})")
                    cols = {row[1] for row in await cursor.fetchall()}
                    assert "domain" in cols, f"{table} missing domain column after migration"

        asyncio.run(run())

    def test_legacy_rows_read_back_with_domain_none(self, tmp_path: Path) -> None:
        db_path = tmp_path / "legacy.db"
        old_schema = """
        CREATE TABLE IF NOT EXISTS gap_runs (
            run_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, needs_json TEXT NOT NULL
        );
        """

        async def run() -> list[GapRun] | None:
            async with aiosqlite.connect(db_path) as db:
                await db.executescript(old_schema)
                await db.execute(
                    "INSERT INTO gap_runs (run_id, timestamp, needs_json) VALUES (?, ?, ?)",
                    ("r-legacy", _TS.isoformat(), "[]"),
                )
                await db.commit()
            store = SqliteSessionStore(db_path)
            return await store.list_gap_runs()

        runs = asyncio.run(run())
        assert runs is not None
        assert len(runs) == 1
        assert runs[0].domain is None


# ---------------------------------------------------------------------------
# GapRun domain round-trip
# ---------------------------------------------------------------------------


class TestGapRunDomain:
    def test_save_and_retrieve_with_domain(self, tmp_path: Path) -> None:
        async def run() -> GapRun | None:
            store = _store(tmp_path / "db.sqlite")
            await store.save_gap_run(_run("Lithium-Ion Batteries"))
            return await store.get_gap_run("r1")

        run_back = asyncio.run(run())
        assert run_back is not None
        assert run_back.domain == "lithium-ion batteries"  # normalised

    def test_none_domain_stored_as_null(self, tmp_path: Path) -> None:
        async def run() -> GapRun | None:
            store = _store(tmp_path / "db.sqlite")
            await store.save_gap_run(GapRun(run_id="r0", timestamp=_TS, needs=[], domain=None))
            return await store.get_gap_run("r0")

        run_back = asyncio.run(run())
        assert run_back is not None
        assert run_back.domain is None


# ---------------------------------------------------------------------------
# Raw findings domain round-trip
# ---------------------------------------------------------------------------


class TestRawFindingsDomain:
    def test_finding_domain_round_trip(self, tmp_path: Path) -> None:
        async def run() -> list[RawFinding]:
            store = _store(tmp_path / "db.sqlite")
            await store.save_gap_run(_run())
            await store.save_raw_findings("r1", [_FINDING])
            return await store.list_raw_findings()

        findings = asyncio.run(run())
        assert len(findings) == 1
        assert findings[0].domain == "lithium-ion batteries"


# ---------------------------------------------------------------------------
# Discards domain round-trip
# ---------------------------------------------------------------------------


class TestDiscardsDomain:
    def test_discard_domain_stored_and_returned(self, tmp_path: Path) -> None:
        async def run() -> list[dict]:
            store = _store(tmp_path / "db.sqlite")
            entry = {
                "title": "T",
                "description": "D",
                "reason": "R",
                "domain": "lithium-ion batteries",
            }
            await store.save_discards("r1", "gap", [entry])
            return await store.list_discards("gap")

        discards = asyncio.run(run())
        assert len(discards) == 1
        assert discards[0]["domain"] == "lithium-ion batteries"
