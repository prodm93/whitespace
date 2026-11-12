"""Gap-run snapshots: written when enabled, harmless when they fail."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from whitespace.agents.council.gap_critic import GapCritic
from whitespace.agents.council.gap_identifier import GapIdentifier
from whitespace.agents.council.gap_synthesiser import GapSynthesiser
from whitespace.orchestration._gap_council_state import GapCouncilState, load_mid_state
from whitespace.orchestration._gap_snapshot import GapSnapshotWriter
from whitespace.orchestration._research_stage import ResearchStage, RunMemory
from whitespace.orchestration.gap_council_graph import GapCouncilGraph
from whitespace.schemas.critique import CriticAssessment, CriticReport
from whitespace.schemas.gap import CandidateGap, GapExploration, UnmetNeed
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import ProposedQuestion


def _state() -> GapCouncilState:
    return {
        "domain": "energy",
        "profile": ProfessionalProfile(),
        "run_id": "run-1",
        "run_memory": RunMemory(prior_queries=["old query"]),
        "findings_text": "- [F1] [web] Kiln heat",
        "candidates": [
            CandidateGap(title="Heat recovery", description="Capture heat", source_model="m")
        ],
        "proposed_questions": [
            ProposedQuestion(
                question="Is waste heat available?",
                purpose="unlock",
                rationale="Decides feasibility",
                hypothesis="Heat is available",
                asker_role="gap_identifier_1",
            )
        ],
    }


def _graph(writer: GapSnapshotWriter | None) -> GapCouncilGraph:
    candidate = CandidateGap(title="Heat recovery", description="Capture heat", source_model="m")
    identifier = MagicMock(spec=GapIdentifier)
    identifier.role_name = "gap_identifier_1"
    identifier.craft_queries = AsyncMock(return_value=["heat recovery"])
    identifier.run = AsyncMock(return_value=GapExploration(gaps=[candidate], findings="Graph"))
    critic = MagicMock(spec=GapCritic)
    critic.run = AsyncMock(
        return_value=CriticReport(
            assessments=[
                CriticAssessment(
                    candidate_id="gap_identifier_1-1", verdict="keep", scores={"specificity": 8}
                )
            ],
            ranking=["gap_identifier_1-1"],
        )
    )
    synthesiser = MagicMock(spec=GapSynthesiser)
    synthesiser.run = AsyncMock(
        return_value=[
            UnmetNeed(
                title="Heat recovery",
                description="Capture heat",
                current_state="Heat is vented",
                why_unmet="No recovery system",
            )
        ]
    )
    research = MagicMock(spec=ResearchStage)
    research.research = AsyncMock(return_value=[])
    research.gate_pool = AsyncMock(side_effect=lambda pool, *_args: (pool, {}))
    return GapCouncilGraph([identifier], critic, synthesiser, research, snapshot_writer=writer)


async def test_writer_saves_state_that_loads_back(tmp_path: Path) -> None:
    state = _state()

    await GapSnapshotWriter(tmp_path / "snapshots").save(state)

    saved = json.loads((tmp_path / "snapshots" / "run-1.json").read_text(encoding="utf-8"))
    restored = load_mid_state(saved)
    assert restored["candidates"] == state["candidates"]
    assert restored["proposed_questions"] == state["proposed_questions"]
    assert restored["run_memory"] == state["run_memory"]
    assert restored["findings_text"] == state["findings_text"]


async def test_writer_swallows_write_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")

    await GapSnapshotWriter(blocker).save(_state())

    assert blocker.read_text(encoding="utf-8") == "x"


async def test_run_saves_one_snapshot_when_writer_present(tmp_path: Path) -> None:
    needs, _ = await _graph(GapSnapshotWriter(tmp_path)).run(
        ProfessionalProfile(), "energy", run_id="run-7"
    )

    assert [need.title for need in needs] == ["Heat recovery"]
    assert [path.name for path in tmp_path.iterdir()] == ["run-7.json"]
    saved = load_mid_state(json.loads((tmp_path / "run-7.json").read_text(encoding="utf-8")))
    assert saved["candidates"][0].candidate_id == "gap_identifier_1-1"


async def test_run_completes_when_snapshot_fails(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")

    needs, _ = await _graph(GapSnapshotWriter(blocker)).run(ProfessionalProfile(), "energy")

    assert [need.title for need in needs] == ["Heat recovery"]


async def test_run_writes_nothing_without_writer(tmp_path: Path) -> None:
    await _graph(None).run(ProfessionalProfile(), "energy")

    assert list(tmp_path.iterdir()) == []
