"""Each tenant's store reads only its own partition of the one sessions table."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from _fake_sessions_table import FakeSessionsTable, install_sessions_table

from whitespace.config import Config
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.research import RawFinding
from whitespace.store import _dynamo_items as items
from whitespace.store.base import GapRun, IdeaRun
from whitespace.store.dynamo_store import DynamoSessionStore
from whitespace.store.noop_store import NoopSessionStore
from whitespace.tenant import TenantIdError

_NEED = UnmetNeed(title="Gap A", description="d", current_state="c", why_unmet="w")
_PROPOSAL = IdeationProposal(
    title="Idea X",
    problem_statement="p",
    technical_approach="t",
    why_this_person="y",
    differentiation_from_prior_art="d",
    limitations="l",
)
_GAP_RUN = GapRun(run_id="gap-a", timestamp=datetime(2026, 7, 1, tzinfo=UTC), needs=[_NEED])
_IDEA_RUN = IdeaRun(
    run_id="idea-a",
    gap_run_id="gap-a",
    timestamp=datetime(2026, 7, 2, tzinfo=UTC),
    proposals=[_PROPOSAL],
)
_FINDING = RawFinding(
    title="t",
    content="c",
    source_type="web",
    source_name="s",
    query="q",
    found_at=datetime(2026, 6, 1, tzinfo=UTC),
)
_DISCARD = {"title": "Old gap", "description": "d", "reason": "r", "domain": "x"}


@pytest.fixture()
def table(monkeypatch: Any) -> FakeSessionsTable:
    return install_sessions_table(monkeypatch)


def _stores() -> tuple[DynamoSessionStore, DynamoSessionStore]:
    return (
        DynamoSessionStore("sessions", "us-east-1", owner="user_a"),
        DynamoSessionStore("sessions", "us-east-1", owner="user_b"),
    )


@pytest.mark.protects("session-store-partition-per-tenant")
@pytest.mark.protects("gap-and-idea-runs-saved")
async def test_gap_runs_are_read_only_by_their_owner(table: FakeSessionsTable) -> None:
    store_a, store_b = _stores()
    await store_a.save_gap_run(_GAP_RUN)

    assert await store_b.list_gap_runs() == []
    assert await store_b.get_latest_gap_run() is None
    assert await store_b.get_gap_run("gap-a") is None
    assert await store_b.get_all_previous_needs() == []
    assert await store_a.list_gap_runs() == [_GAP_RUN]
    assert await store_a.get_latest_gap_run() == _GAP_RUN
    assert await store_a.get_gap_run("gap-a") == _GAP_RUN
    assert await store_a.get_all_previous_needs() == [_NEED]
    assert [item["pk"] for item in table.items] == ["USER#user_a#GAPRUN"]


@pytest.mark.protects("session-store-partition-per-tenant")
@pytest.mark.protects("gap-and-idea-runs-saved")
async def test_idea_runs_are_read_only_by_their_owner(table: FakeSessionsTable) -> None:
    store_a, store_b = _stores()
    await store_a.save_idea_run(_IDEA_RUN)

    assert await store_b.list_idea_runs() == []
    assert await store_b.get_idea_run("idea-a") is None
    assert await store_b.get_all_previous_proposals() == []
    assert await store_a.list_idea_runs() == [_IDEA_RUN]
    assert await store_a.get_idea_run("idea-a") == _IDEA_RUN
    assert await store_a.get_all_previous_proposals() == [_PROPOSAL]
    assert [item["pk"] for item in table.items] == ["USER#user_a#IDEARUN"]


@pytest.mark.protects("session-store-partition-per-tenant")
async def test_raw_findings_are_read_only_by_their_owner(table: FakeSessionsTable) -> None:
    store_a, store_b = _stores()
    await store_a.save_raw_findings("gap-a", [_FINDING])

    assert await store_b.list_raw_findings() == []
    assert await store_b.list_raw_findings("gap-a") == []
    assert await store_a.list_raw_findings("gap-a") == [_FINDING]
    assert [item["pk"] for item in table.items] == ["USER#user_a#FINDINGS"]


@pytest.mark.protects("session-store-partition-per-tenant")
async def test_discards_are_read_only_by_their_owner(table: FakeSessionsTable) -> None:
    store_a, store_b = _stores()
    await store_a.save_discards("gap-a", "gap", [_DISCARD])

    assert await store_b.list_discards() == []
    assert await store_b.list_discards("gap") == []
    assert await store_a.list_discards("gap") == [{"kind": "gap", **_DISCARD}]
    assert [item["pk"] for item in table.items] == ["USER#user_a#DISCARD#gap"]


@pytest.mark.parametrize("owner", ["", "default"])
@pytest.mark.protects("tenant-id-validated")
def test_a_store_for_an_empty_or_default_owner_is_refused(owner: str) -> None:
    with pytest.raises(TenantIdError):
        DynamoSessionStore("t", "r", owner=owner)


@pytest.mark.protects("tenant-id-validated")
def test_a_store_without_an_owner_cannot_be_built() -> None:
    with pytest.raises(TypeError):
        DynamoSessionStore("t", "r")  # type: ignore[call-arg]


def test_the_api_in_saas_mode_builds_no_shared_dynamo_store() -> None:
    from whitespace.api.app import _build_store

    config = Config(_env_file=None, mode="saas", sessions_table="x")

    assert isinstance(_build_store(config), NoopSessionStore)


class TestPartitionKeysPerTenant:
    @pytest.mark.protects("session-store-partition-per-tenant")
    def test_each_key_names_its_owner(self) -> None:
        assert items.gap_run_pk("user_a") == "USER#user_a#GAPRUN"
        assert items.idea_run_pk("user_a") == "USER#user_a#IDEARUN"
        assert items.findings_pk("user_a") == "USER#user_a#FINDINGS"
        assert items.discard_pk("user_a", "gap") == "USER#user_a#DISCARD#gap"

    @pytest.mark.protects("session-store-partition-per-tenant")
    def test_two_owners_never_share_a_partition(self) -> None:
        assert items.gap_run_to_item("user_a", _GAP_RUN)["pk"] == "USER#user_a#GAPRUN"
        assert items.gap_run_to_item("user_b", _GAP_RUN)["pk"] == "USER#user_b#GAPRUN"
