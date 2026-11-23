"""A gap run keeps the profile it was made with, in SQLite and in DynamoDB."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import pytest
from _fake_sessions_table import install_sessions_table
from pydantic import ValidationError

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.store import _dynamo_items as items
from whitespace.store.base import GapRun, SessionStore
from whitespace.store.dynamo_store import DynamoSessionStore
from whitespace.store.sqlite_store import SqliteSessionStore

_TS = datetime(2026, 11, 1, tzinfo=UTC)
_NEED = UnmetNeed(title="Gap A", description="d", current_state="c", why_unmet="w")
_PROFILE = ProfessionalProfile(hard_skills=["battery management"], domain_knowledge=["energy"])


def _run(run_id: str = "r1", profile: ProfessionalProfile | None = _PROFILE) -> GapRun:
    return GapRun(run_id=run_id, timestamp=_TS, needs=[_NEED], domain="energy", profile=profile)


@pytest.fixture(params=["sqlite", "dynamodb"])
def store(request: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SessionStore:
    if request.param == "sqlite":
        return SqliteSessionStore(tmp_path / "s.db")
    install_sessions_table(monkeypatch)
    return DynamoSessionStore("sessions", "us-east-1", owner="user_a")


async def test_a_run_saved_with_a_profile_loads_with_it(store: SessionStore) -> None:
    await store.save_gap_run(_run())

    loaded = await store.get_latest_gap_run()

    assert loaded is not None and loaded.profile == _PROFILE


async def test_a_run_saved_without_a_profile_loads_with_none(store: SessionStore) -> None:
    await store.save_gap_run(_run(profile=None))

    loaded = await store.get_gap_run("r1")

    assert loaded is not None and loaded.profile is None


async def test_an_existing_sqlite_file_with_no_profile_column_opens_and_works(
    tmp_path: Path,
) -> None:
    path = tmp_path / "old.db"
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "CREATE TABLE gap_runs (run_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,"
            " needs_json TEXT NOT NULL, domain TEXT)"
        )
        await db.execute(
            "INSERT INTO gap_runs (run_id, timestamp, needs_json, domain) VALUES (?, ?, ?, ?)",
            ("old-run", _TS.isoformat(), json.dumps([_NEED.model_dump()]), "energy"),
        )
        await db.commit()
    store = SqliteSessionStore(path)

    old = await store.get_gap_run("old-run")
    await store.save_gap_run(_run("new-run"))
    new = await store.get_gap_run("new-run")

    assert old is not None and old.profile is None
    assert new is not None and new.profile == _PROFILE


def test_an_old_dynamodb_item_with_no_profile_loads_with_none() -> None:
    item = items.gap_run_to_item("user_a", _run(profile=None))
    payload = json.loads(item["payload"])
    del payload["profile"]

    loaded = items.item_to_gap_run({**item, "payload": json.dumps(payload)})

    assert loaded.profile is None


def test_a_dynamodb_item_whose_profile_is_not_valid_fails_the_load() -> None:
    item = items.gap_run_to_item("user_a", _run())
    payload = json.loads(item["payload"])
    payload["profile"] = {"hard_skills": "not a list"}

    with pytest.raises(ValidationError):
        items.item_to_gap_run({**item, "payload": json.dumps(payload)})
