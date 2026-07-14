"""Tests for DynamoDB item marshalling."""

from __future__ import annotations

from datetime import UTC, datetime

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.research import RawFinding
from whitespace.store import _dynamo_items as items
from whitespace.store.base import GapRun, IdeaRun

SAMPLE_NEED = UnmetNeed(
    title="Thermal runaway detection lag",
    description="Existing sensors detect thermal runaway too late for safe cell isolation",
    current_state="Voltage-drop based detection triggers after propagation has begun",
    why_unmet="No cost-effective early-stage gas sensing at the cell level",
    matching_skills=["battery management systems", "embedded sensing"],
)

SAMPLE_PROPOSAL = IdeationProposal(
    title="Cell-level gas-composition early warning",
    problem_statement="Thermal runaway detection lags behind gas venting onset",
    technical_approach="Miniaturised electrochemical gas sensor per cell group",
    why_this_person="Background in embedded sensing and battery management systems",
    differentiation_from_prior_art="Existing patents rely on voltage or temperature only",
    limitations="Added bill-of-materials cost per cell group",
)


def _gap_run() -> GapRun:
    return GapRun(
        run_id="gap-run-1",
        timestamp=datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC),
        needs=[SAMPLE_NEED],
    )


def _idea_run() -> IdeaRun:
    return IdeaRun(
        run_id="idea-run-1",
        gap_run_id="gap-run-1",
        selected_need_titles=[SAMPLE_NEED.title],
        timestamp=datetime(2026, 7, 2, 9, 30, 0, tzinfo=UTC),
        proposals=[SAMPLE_PROPOSAL],
    )


def _finding() -> RawFinding:
    return RawFinding(
        title="Early gas detection in lithium-ion packs",
        content="A sensor array positioned within the cell group...",
        source_type="paper",
        source_name="Journal of Power Sources",
        query="thermal runaway early detection",
        found_at=datetime(2026, 6, 15, 8, 0, 0, tzinfo=UTC),
    )


class TestGapRunItem:
    def test_round_trip(self) -> None:
        run = _gap_run()
        item = items.gap_run_to_item(run)
        assert items.item_to_gap_run(item) == run

    def test_partition_key(self) -> None:
        item = items.gap_run_to_item(_gap_run())
        assert item["pk"] == items.GAPRUN_PK

    def test_sort_key_carries_timestamp_and_run_id(self) -> None:
        run = _gap_run()
        item = items.gap_run_to_item(run)
        assert item["sk"] == f"{run.timestamp.isoformat()}#{run.run_id}"

    def test_needs_extracted_from_item(self) -> None:
        item = items.gap_run_to_item(_gap_run())
        assert items.needs_from_gap_run_item(item) == [SAMPLE_NEED]


class TestIdeaRunItem:
    def test_round_trip(self) -> None:
        run = _idea_run()
        item = items.idea_run_to_item(run)
        assert items.item_to_idea_run(item) == run

    def test_partition_key(self) -> None:
        item = items.idea_run_to_item(_idea_run())
        assert item["pk"] == items.IDEARUN_PK

    def test_gap_run_id_carried_as_own_attribute(self) -> None:
        run = _idea_run()
        item = items.idea_run_to_item(run)
        assert item["gap_run_id"] == run.gap_run_id

    def test_proposals_extracted_from_item(self) -> None:
        item = items.idea_run_to_item(_idea_run())
        assert items.proposals_from_idea_run_item(item) == [SAMPLE_PROPOSAL]


class TestFindingItem:
    def test_round_trip(self) -> None:
        finding = _finding()
        item = items.finding_to_item("gap-run-1", finding)
        assert items.item_to_finding(item) == finding

    def test_partition_key(self) -> None:
        item = items.finding_to_item("gap-run-1", _finding())
        assert item["pk"] == items.FINDINGS_PK

    def test_run_id_carried_as_own_attribute(self) -> None:
        item = items.finding_to_item("gap-run-1", _finding())
        assert item["run_id"] == "gap-run-1"

    def test_sort_key_starts_with_found_at(self) -> None:
        finding = _finding()
        item = items.finding_to_item("gap-run-1", finding)
        assert item["sk"].startswith(finding.found_at.isoformat())


class TestDiscardItem:
    def test_round_trip(self) -> None:
        entry = {"title": "Duplicate idea", "description": "Same as an earlier candidate"}
        item = items.discard_to_item("idea-run-1", "idea", entry)
        discard = items.item_to_discard(item)
        assert discard["title"] == entry["title"]
        assert discard["description"] == entry["description"]
        assert discard["kind"] == "idea"

    def test_partition_key_scoped_to_kind(self) -> None:
        item = items.discard_to_item("idea-run-1", "idea", {})
        assert item["pk"] == items.discard_pk("idea")
        assert item["pk"] != items.discard_pk("gap")

    def test_missing_fields_default_to_empty_string(self) -> None:
        item = items.discard_to_item("idea-run-1", "idea", {})
        discard = items.item_to_discard(item)
        assert discard["title"] == ""
        assert discard["reason"] == ""


class TestGapRunDomain:
    def test_domain_survives_round_trip(self) -> None:
        run = GapRun(
            run_id="r1",
            timestamp=datetime(2026, 7, 1, tzinfo=UTC),
            needs=[],
            domain="lithium-ion batteries",
        )
        item = items.gap_run_to_item(run)
        assert items.item_to_gap_run(item).domain == "lithium-ion batteries"

    def test_none_domain_survives_round_trip(self) -> None:
        run = GapRun(run_id="r2", timestamp=datetime(2026, 7, 1, tzinfo=UTC), needs=[], domain=None)
        item = items.gap_run_to_item(run)
        assert items.item_to_gap_run(item).domain is None


class TestDiscardDomain:
    def test_domain_stored_and_returned(self) -> None:
        entry = {"title": "T", "description": "D", "reason": "R", "domain": "robotics"}
        item = items.discard_to_item("r1", "gap", entry)
        discard = items.item_to_discard(item)
        assert discard["domain"] == "robotics"

    def test_missing_domain_defaults_to_empty_string(self) -> None:
        item = items.discard_to_item("r1", "gap", {"title": "T", "description": "D"})
        assert items.item_to_discard(item)["domain"] == ""


class TestSortKeyOrdering:
    def test_later_gap_run_sorts_after_earlier_as_plain_string(self) -> None:
        earlier = GapRun(run_id="a", timestamp=datetime(2026, 1, 1, tzinfo=UTC), needs=[])
        later = GapRun(run_id="b", timestamp=datetime(2026, 6, 1, tzinfo=UTC), needs=[])
        earlier_sk = items.gap_run_to_item(earlier)["sk"]
        later_sk = items.gap_run_to_item(later)["sk"]
        assert earlier_sk < later_sk

    def test_later_finding_sorts_after_earlier_as_plain_string(self) -> None:
        earlier = RawFinding(
            title="t",
            content="c",
            source_type="web",
            source_name="s",
            query="q",
            found_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        later = RawFinding(
            title="t",
            content="c",
            source_type="web",
            source_name="s",
            query="q",
            found_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        earlier_sk = items.finding_to_item("run", earlier)["sk"]
        later_sk = items.finding_to_item("run", later)["sk"]
        assert earlier_sk < later_sk
