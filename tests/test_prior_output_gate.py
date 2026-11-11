from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from _question_gate_helpers import FakeDedup

from whitespace.orchestration._memory import load_ideation_prior_texts
from whitespace.orchestration._prior_output_gate import gate_against_prior
from whitespace.schemas.gap import CandidateGap
from whitespace.schemas.idea import IdeationProposal
from whitespace.store.base import GapRun, IdeaRun
from whitespace.store.sqlite_store import SqliteSessionStore


def _gap(candidate_id: str, title: str) -> CandidateGap:
    return CandidateGap(
        title=title,
        description=f"{title} description",
        source_model="m",
        candidate_id=candidate_id,
    )


async def test_scores_kill_flag_or_keep_each_candidate() -> None:
    dedup = FakeDedup([(0.95, "prior A"), (0.90, "prior B"), (0.50, "prior C")])
    pool = [_gap("g-1", "Duplicate"), _gap("g-2", "Close"), _gap("g-3", "Fresh")]

    kept, flags, kills = await gate_against_prior(cast(Any, dedup), pool, ["prior text"])

    assert [c.candidate_id for c in kept] == ["g-2", "g-3"]
    assert flags == {"g-2": "resembles prior work (score 0.90): prior B"}
    assert kills == [
        {
            "title": "Duplicate",
            "description": "Duplicate description",
            "reason": "near-duplicate of a previous run's output",
        }
    ]


async def test_ideation_prior_texts_hold_proposals_and_idea_discards(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "s.db")
    proposal = IdeationProposal(
        title="Acoustic cell monitor",
        problem_statement="Runaway is detected too late",
        technical_approach="Ultrasound in the module housing",
        why_this_person="Signal processing background",
        differentiation_from_prior_art="Passive listening only",
        limitations="Noise floor in vehicles",
    )
    await store.save_gap_run(GapRun(run_id="gap-1", timestamp=datetime(2026, 11, 1, tzinfo=UTC)))
    await store.save_idea_run(
        IdeaRun(
            run_id="idea-1",
            gap_run_id="gap-1",
            timestamp=datetime(2026, 11, 1, tzinfo=UTC),
            proposals=[proposal],
        )
    )
    await store.save_discards(
        "idea-1", "idea", [{"title": "Gas sniffer", "description": "MOS sensor", "reason": "dup"}]
    )
    await store.save_discards(
        "gap-1", "gap", [{"title": "Gap kill", "description": "Not an idea", "reason": "dup"}]
    )

    texts = await load_ideation_prior_texts(store)

    assert texts == [
        "Acoustic cell monitor: Runaway is detected too late",
        "Gas sniffer: MOS sensor",
    ]
    assert await load_ideation_prior_texts(None) == []
