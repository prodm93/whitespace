"""A repeated save in DynamoDB leaves one row for each finding."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from _fake_sessions_table import install_sessions_table

from whitespace.schemas.research import RawFinding
from whitespace.store.base import SessionStore
from whitespace.store.dynamo_store import DynamoSessionStore
from whitespace.store.sqlite_store import SqliteSessionStore


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
