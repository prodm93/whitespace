"""A repeated save in DynamoDB leaves one run, and one row for each rejection and finding."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from _fake_sessions_table import install_sessions_table

from whitespace.orchestration._run_records import save_gap_result, save_idea_result
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.research import RawFinding
from whitespace.store.base import SessionStore
from whitespace.store.dynamo_store import DynamoSessionStore
from whitespace.store.sqlite_store import SqliteSessionStore

_NEED = UnmetNeed(title="Gap A", description="d", current_state="c", why_unmet="w")
_OTHER_NEED = UnmetNeed(title="Gap B", description="d", current_state="c", why_unmet="w")
_PROPOSAL = IdeationProposal(
    title="Idea X",
    problem_statement="p",
    technical_approach="t",
    why_this_person="y",
    differentiation_from_prior_art="d",
    limitations="l",
)
_KILL = {"title": "Kill A", "description": "d", "reason": "Covered by US1", "domain": "x"}


def _finding(link: str = "https://example.org/1", query: str = "q") -> RawFinding:
    return RawFinding(
        title="t",
        content="c",
        source_type="web",
        source_url=link,
        source_name="s",
        query=query,
        found_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


@pytest.fixture()
def dynamo(monkeypatch: pytest.MonkeyPatch) -> DynamoSessionStore:
    install_sessions_table(monkeypatch)
    return DynamoSessionStore("sessions", "us-east-1", owner="user_a")


@pytest.fixture(params=["dynamodb", "sqlite"])
def store(request: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SessionStore:
    if request.param == "sqlite":
        return SqliteSessionStore(tmp_path / "s.db")
    install_sessions_table(monkeypatch)
    return DynamoSessionStore("sessions", "us-east-1", owner="user_a")


@pytest.mark.protects("repeated-save-stores-once")
async def test_a_gap_result_saved_twice_leaves_one_run_and_the_same_rejections(
    dynamo: DynamoSessionStore,
) -> None:
    await save_gap_result(dynamo, "run-1", "energy", [_NEED], [_KILL])
    after_first = len(await dynamo.list_discards())
    await save_gap_result(dynamo, "run-1", "energy", [_NEED], [_KILL])

    assert [run.run_id for run in await dynamo.list_gap_runs()] == ["run-1"]
    assert len(await dynamo.list_discards()) == after_first == 1


@pytest.mark.protects("repeated-save-stores-once")
async def test_an_idea_result_saved_twice_leaves_one_run(dynamo: DynamoSessionStore) -> None:
    await save_idea_result(dynamo, "idea-1", "run-1", ["Gap A"], [_PROPOSAL], [_KILL])
    await save_idea_result(dynamo, "idea-1", "run-1", ["Gap A"], [_PROPOSAL], [_KILL])

    assert [run.run_id for run in await dynamo.list_idea_runs()] == ["idea-1"]
    assert len(await dynamo.list_discards("idea")) == 1


async def test_a_second_save_with_changed_needs_leaves_one_run_with_the_new_needs(
    dynamo: DynamoSessionStore,
) -> None:
    await save_gap_result(dynamo, "run-1", "energy", [_NEED])
    await save_gap_result(dynamo, "run-1", "energy", [_OTHER_NEED])

    runs = await dynamo.list_gap_runs()
    assert [run.needs for run in runs] == [[_OTHER_NEED]]
    latest = await dynamo.get_latest_gap_run()
    assert latest is not None and latest.needs == [_OTHER_NEED]


async def test_two_runs_stay_two(dynamo: DynamoSessionStore) -> None:
    await save_gap_result(dynamo, "run-1", "energy", [_NEED])
    await save_gap_result(dynamo, "run-2", "energy", [_NEED])

    assert sorted(run.run_id for run in await dynamo.list_gap_runs()) == ["run-1", "run-2"]


async def test_equal_rejections_of_two_runs_stay_two(dynamo: DynamoSessionStore) -> None:
    await dynamo.save_discards("run-1", "gap", [_KILL])
    await dynamo.save_discards("run-2", "gap", [_KILL])

    assert len(await dynamo.list_discards("gap")) == 2


async def test_two_equal_rejections_in_one_save_are_stored_once(
    dynamo: DynamoSessionStore,
) -> None:
    await dynamo.save_discards("run-1", "gap", [_KILL, dict(_KILL)])

    assert len(await dynamo.list_discards("gap")) == 1


async def test_rejections_are_listed_newest_first(
    dynamo: DynamoSessionStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    times = iter(datetime(2026, 11, 1, hour, tzinfo=UTC) for hour in range(3))

    class _Clock:
        @staticmethod
        def now(_tz: Any) -> datetime:
            return next(times)

    monkeypatch.setattr("whitespace.store._dynamo_items.datetime", _Clock)
    await dynamo.save_discards("run-1", "gap", [{**_KILL, "title": "first"}])
    await dynamo.save_discards("run-2", "gap", [{**_KILL, "title": "second"}])
    await dynamo.save_discards("run-3", "idea", [{**_KILL, "title": "third"}])

    assert [d["title"] for d in await dynamo.list_discards()] == ["third", "second", "first"]


@pytest.mark.protects("repeated-save-stores-once")
async def test_findings_saved_twice_for_one_run_are_each_stored_once(
    dynamo: DynamoSessionStore,
) -> None:
    findings = [_finding("https://example.org/1"), _finding("https://example.org/2")]

    await dynamo.save_raw_findings("run-1", findings)
    await dynamo.save_raw_findings("run-1", findings)

    links = sorted(f.source_url or "" for f in await dynamo.list_raw_findings("run-1"))
    assert links == ["https://example.org/1", "https://example.org/2"]


async def test_one_finding_in_two_runs_is_stored_for_both(dynamo: DynamoSessionStore) -> None:
    await dynamo.save_raw_findings("run-1", [_finding()])
    await dynamo.save_raw_findings("run-2", [_finding()])

    assert len(await dynamo.list_raw_findings("run-1")) == 1
    assert len(await dynamo.list_raw_findings("run-2")) == 1


def _split_pair(mark: str) -> list[RawFinding]:
    return [_finding(f"a{mark}b", "c"), _finding("a", f"b{mark}c")]


def _parts(findings: list[RawFinding]) -> list[tuple[str, str]]:
    return sorted((f.source_url or "", f.query) for f in findings)


@pytest.mark.protects("repeated-save-stores-once")
@pytest.mark.parametrize("mark", ["\x1f", '","'], ids=["unit separator", "quote and comma"])
async def test_two_findings_split_the_same_two_ways_are_both_stored_in_one_call(
    store: SessionStore, mark: str
) -> None:
    pair = _split_pair(mark)

    await store.save_raw_findings("run-1", pair)

    assert _parts(await store.list_raw_findings("run-1")) == _parts(pair)


async def test_two_findings_split_the_same_two_ways_are_both_stored_in_two_calls(
    store: SessionStore,
) -> None:
    first, second = _split_pair("\x1f")

    await store.save_raw_findings("run-1", [first])
    await store.save_raw_findings("run-1", [second])

    assert _parts(await store.list_raw_findings("run-1")) == _parts([first, second])


async def test_two_rejections_split_the_same_two_ways_are_both_stored(
    store: SessionStore,
) -> None:
    pair = [
        {"title": "a\x1fb", "description": "c", "reason": "r"},
        {"title": "a", "description": "b\x1fc", "reason": "r"},
    ]

    await store.save_discards("run-1", "gap", pair)

    stored = sorted((d["title"], d["description"]) for d in await store.list_discards("gap"))
    assert stored == [("a", "b\x1fc"), ("a\x1fb", "c")]
