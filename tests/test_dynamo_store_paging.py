"""DynamoDB list reads follow every page of a long history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from _fake_sessions_table import FakeSessionsTable, install_sessions_table

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.research import RawFinding
from whitespace.store.base import GapRun
from whitespace.store.dynamo_store import DynamoSessionStore

_NEED = UnmetNeed(title="Gap A", description="d", current_state="c", why_unmet="w")
_START = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture()
def table(monkeypatch: pytest.MonkeyPatch) -> FakeSessionsTable:
    table = install_sessions_table(monkeypatch)
    table.page_size = 2
    return table


def _store() -> DynamoSessionStore:
    return DynamoSessionStore("sessions", "us-east-1", owner="user_a")


async def _five_runs(store: DynamoSessionStore) -> None:
    for day in range(5):
        run = GapRun(run_id=f"run-{day}", timestamp=_START + timedelta(days=day), needs=[_NEED])
        await store.save_gap_run(run)


@pytest.mark.protects("long-history-read-in-full")
async def test_every_run_of_a_long_history_is_listed(table: FakeSessionsTable) -> None:
    store = _store()
    await _five_runs(store)

    runs = await store.list_gap_runs()

    assert [run.run_id for run in runs] == ["run-4", "run-3", "run-2", "run-1", "run-0"]


async def test_the_oldest_run_is_found_by_its_id(table: FakeSessionsTable) -> None:
    store = _store()
    await _five_runs(store)

    found = await store.get_gap_run("run-0")

    assert found is not None and found.run_id == "run-0"


@pytest.mark.protects("long-history-read-in-full")
async def test_every_rejection_and_finding_is_listed(table: FakeSessionsTable) -> None:
    store = _store()
    kills = [{"title": f"Kill {n}", "description": "d", "reason": "r"} for n in range(5)]
    findings = [
        RawFinding(
            title="t",
            content="c",
            source_type="web",
            source_url=f"https://example.org/{n}",
            source_name="s",
            query="q",
            found_at=_START + timedelta(days=n),
        )
        for n in range(5)
    ]
    await store.save_discards("run-1", "gap", kills)
    await store.save_raw_findings("run-1", findings)

    assert len(await store.list_discards("gap")) == 5
    assert len(await store.list_raw_findings("run-1")) == 5


async def test_a_history_past_the_page_cap_raises_instead_of_being_cut(
    table: FakeSessionsTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    import whitespace.store.dynamo_store as module

    monkeypatch.setattr(module, "_MAX_PAGES", 2)
    store = _store()
    await _five_runs(store)

    with pytest.raises(RuntimeError, match="more than 2 pages"):
        await store.list_gap_runs()


async def test_the_latest_run_is_read_with_one_query(table: FakeSessionsTable) -> None:
    store = _store()
    await _five_runs(store)
    table.query_calls = 0

    latest = await store.get_latest_gap_run()

    assert latest is not None and latest.run_id == "run-4"
    assert table.query_calls == 1
