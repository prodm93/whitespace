"""Tests for DynamoDB item marshalling."""

from __future__ import annotations

from datetime import UTC, datetime

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.research import RawFinding
from whitespace.store import _dynamo_items as items
from whitespace.store._identities import identity_digest
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
        item = items.gap_run_to_item("user_a", run)
        assert items.item_to_gap_run(item) == run

    def test_partition_key(self) -> None:
        item = items.gap_run_to_item("user_a", _gap_run())
        assert item["pk"] == "USER#user_a#GAPRUN"

    def test_sort_key_carries_timestamp_and_run_id(self) -> None:
        run = _gap_run()
        item = items.gap_run_to_item("user_a", run)
        assert item["sk"] == f"{run.timestamp.isoformat()}#{run.run_id}"

    def test_needs_extracted_from_item(self) -> None:
        item = items.gap_run_to_item("user_a", _gap_run())
        assert items.needs_from_gap_run_item(item) == [SAMPLE_NEED]


class TestIdeaRunItem:
    def test_round_trip(self) -> None:
        run = _idea_run()
        item = items.idea_run_to_item("user_a", run)
        assert items.item_to_idea_run(item) == run

    def test_partition_key(self) -> None:
        item = items.idea_run_to_item("user_a", _idea_run())
        assert item["pk"] == "USER#user_a#IDEARUN"

    def test_gap_run_id_carried_as_own_attribute(self) -> None:
        run = _idea_run()
        item = items.idea_run_to_item("user_a", run)
        assert item["gap_run_id"] == run.gap_run_id

    def test_proposals_extracted_from_item(self) -> None:
        item = items.idea_run_to_item("user_a", _idea_run())
        assert items.proposals_from_idea_run_item(item) == [SAMPLE_PROPOSAL]


class TestFindingItem:
    def test_round_trip(self) -> None:
        finding = _finding()
        item = items.finding_to_item("user_a", "gap-run-1", finding)
        assert items.item_to_finding(item) == finding

    def test_partition_key(self) -> None:
        item = items.finding_to_item("user_a", "gap-run-1", _finding())
        assert item["pk"] == "USER#user_a#FINDINGS"

    def test_run_id_carried_as_own_attribute(self) -> None:
        item = items.finding_to_item("user_a", "gap-run-1", _finding())
        assert item["run_id"] == "gap-run-1"

    def test_found_at_carried_as_own_attribute(self) -> None:
        finding = _finding()
        item = items.finding_to_item("user_a", "gap-run-1", finding)
        assert item["found_at"] == finding.found_at.isoformat()

    def test_sort_key_is_the_run_id_and_a_digest_of_the_identity(self) -> None:
        finding = _finding()
        item = items.finding_to_item("user_a", "gap-run-1", finding)
        refetched = finding.model_copy(update={"found_at": datetime(2026, 7, 1, tzinfo=UTC)})
        run_id, digest = item["sk"].rsplit("#", 1)
        assert run_id == "gap-run-1"
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")
        assert items.finding_to_item("user_a", "gap-run-1", refetched)["sk"] == item["sk"]


class TestDiscardItem:
    def test_round_trip(self) -> None:
        entry = {"title": "Duplicate idea", "description": "Same as an earlier candidate"}
        item = items.discard_to_item("user_a", "idea-run-1", "idea", entry)
        discard = items.item_to_discard(item)
        assert discard["title"] == entry["title"]
        assert discard["description"] == entry["description"]
        assert discard["kind"] == "idea"

    def test_partition_key_scoped_to_kind(self) -> None:
        item = items.discard_to_item("user_a", "idea-run-1", "idea", {})
        assert item["pk"] == "USER#user_a#DISCARD#idea"
        assert item["pk"] != "USER#user_a#DISCARD#gap"

    def test_missing_fields_default_to_empty_string(self) -> None:
        item = items.discard_to_item("user_a", "idea-run-1", "idea", {})
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
        item = items.gap_run_to_item("user_a", run)
        assert items.item_to_gap_run(item).domain == "lithium-ion batteries"

    def test_none_domain_survives_round_trip(self) -> None:
        run = GapRun(run_id="r2", timestamp=datetime(2026, 7, 1, tzinfo=UTC), needs=[], domain=None)
        item = items.gap_run_to_item("user_a", run)
        assert items.item_to_gap_run(item).domain is None


class TestDiscardDomain:
    def test_domain_stored_and_returned(self) -> None:
        entry = {"title": "T", "description": "D", "reason": "R", "domain": "robotics"}
        item = items.discard_to_item("user_a", "r1", "gap", entry)
        discard = items.item_to_discard(item)
        assert discard["domain"] == "robotics"

    def test_missing_domain_defaults_to_empty_string(self) -> None:
        item = items.discard_to_item("user_a", "r1", "gap", {"title": "T", "description": "D"})
        assert items.item_to_discard(item)["domain"] == ""


class TestSortKeyOrdering:
    def test_later_gap_run_sorts_after_earlier_as_plain_string(self) -> None:
        earlier = GapRun(run_id="a", timestamp=datetime(2026, 1, 1, tzinfo=UTC), needs=[])
        later = GapRun(run_id="b", timestamp=datetime(2026, 6, 1, tzinfo=UTC), needs=[])
        earlier_sk = items.gap_run_to_item("user_a", earlier)["sk"]
        later_sk = items.gap_run_to_item("user_a", later)["sk"]
        assert earlier_sk < later_sk


class TestIdentityDigest:
    def test_parts_split_the_same_two_ways_give_different_digests(self) -> None:
        first = identity_digest(("web", "a\x1fb", "c"))
        second = identity_digest(("web", "a", "b\x1fc"))
        assert first != second

    def test_one_identity_gives_the_same_digest_each_time(self) -> None:
        assert identity_digest(("web", "a", "c")) == identity_digest(["web", "a", "c"])

    def test_the_digest_is_64_hexadecimal_characters(self) -> None:
        digest = identity_digest(("paper", "Journal", "q"))
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")


class TestDiscardKey:
    def test_sort_key_is_the_run_id_and_a_digest_and_created_at_is_kept(self) -> None:
        entry = {"title": "T", "description": "D", "reason": "R"}
        item = items.discard_to_item("user_a", "r1", "gap", entry)
        again = items.discard_to_item("user_a", "r1", "gap", dict(entry))
        assert item["sk"].startswith("r1#") and item["sk"] == again["sk"]
        assert datetime.fromisoformat(item["created_at"]).tzinfo is not None
