"""Ideation second half with the user's answers: refine, duplicate gate, novelty recheck."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from _gap_council_helpers import ScoreDedup

from whitespace.agents.council.idea_critic import IdeaCritic
from whitespace.agents.council.idea_ideator import IdeaIdeator
from whitespace.agents.council.idea_synthesiser import IdeaSynthesiser
from whitespace.orchestration._ideation_council_state import IdeationCouncilState
from whitespace.orchestration.ideation_council_graph import IdeationCouncilGraph
from whitespace.schemas.critique import CandidateLike, CriticAssessment, CriticReport
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import CandidateIdea
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import QuestionRecord, UserAnswer

ROLES = ("idea_ideator_1", "idea_ideator_2")
_ANSWER = [UserAnswer(question_id="q-1", status="answered", answer="Sealed packs only")]


@dataclass
class IdeaRouter:
    """Scripted replies per role and response format; records every call."""

    refine: dict[str, dict[str, Any]] = field(default_factory=dict)
    queries: dict[str, list[list[str]]] = field(default_factory=dict)
    decisions: dict[str, list[list[dict[str, Any]]]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def call(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        role, fmt = kwargs["role"], kwargs["response_format"]
        name = fmt.get("json_schema", {}).get("name", "json_object")
        if name == "RefinedCandidateIdeas":
            reply = self.refine.get(role, {"ideas": [], "new_ideas": []})
        elif name == "json_object":
            reply = {"queries": self._pop(self.queries, role, ["q1", "q2"])}
        elif name == "NoveltyDecisions":
            reply = {"decisions": self._pop(self.decisions, role, [])}
        else:
            reply = {"ideas": []}
        return {"model_id": f"{role}-model", "content": json.dumps(reply)}

    @staticmethod
    def _pop(table: dict[str, list[Any]], role: str, default: Any) -> Any:
        queue = table.get(role, [])
        return queue.pop(0) if queue else default

    def named(self, role: str, name: str) -> list[dict[str, Any]]:
        return [
            c
            for c in self.calls
            if c["role"] == role
            and c["response_format"].get("json_schema", {}).get("name", "json_object") == name
        ]


@dataclass
class PriorArt:
    received: list[list[str]] = field(default_factory=list)

    async def research(self, queries: list[str], per_query: int = 5) -> list[Any]:
        self.received.append(list(queries))
        return []


def _idea(role: str, n: int, title: str) -> CandidateIdea:
    return CandidateIdea(
        title=title,
        description=f"{title} description",
        source_model=f"{role}-model",
        candidate_id=f"{role}-{n}",
        source_role=role,
    )


def _record(purpose: str = "clarify", related: str = "") -> QuestionRecord:
    return QuestionRecord(
        question_id="q-1",
        run_id="job-1",
        stage="ideation",
        purpose=purpose,  # type: ignore[arg-type]
        question="Which packs?",
        hypothesis="Pouch cells",
        rationale="r",
        asker_role="idea_ideator_1",
        related_candidate_id=related,
        asked=True,
        created_at=datetime(2026, 11, 11, tzinfo=UTC),
    )


def _keep_all(candidates: list[CandidateLike], *_args: Any, **_kw: Any) -> CriticReport:
    ids = [c.candidate_id for c in candidates]
    return CriticReport(
        assessments=[
            CriticAssessment(candidate_id=i, verdict="keep", scores={"specificity": 8}) for i in ids
        ],
        ranking=ids,
    )


@dataclass
class Council:
    graph: IdeationCouncilGraph
    router: IdeaRouter
    prior_art: PriorArt
    critic: MagicMock
    synthesiser: MagicMock


def _council(router: IdeaRouter, dedup: ScoreDedup | None = None) -> Council:
    ideators = [IdeaIdeator(MagicMock(), router, role) for role in ROLES]  # type: ignore[arg-type]
    critic = MagicMock(spec=IdeaCritic)
    critic.run = AsyncMock(side_effect=_keep_all)
    synthesiser = MagicMock(spec=IdeaSynthesiser)
    synthesiser.run = AsyncMock(return_value=[])
    prior_art = PriorArt()
    graph = IdeationCouncilGraph(
        ideators,
        critic,
        synthesiser,
        prior_art,  # type: ignore[arg-type]
        dedup or ScoreDedup(),  # type: ignore[arg-type]
    )
    return Council(graph, router, prior_art, critic, synthesiser)


def _mid_state(questions: list[QuestionRecord]) -> IdeationCouncilState:
    return {
        "selected_needs": [
            UnmetNeed(title="Early warning", description="d", current_state="s", why_unmet="w")
        ],
        "profile": ProfessionalProfile(),
        "graph_context": "Graph context",
        "run_id": "job-1",
        "gap_run_id": "gap-1",
        "domain": "batteries",
        "candidates": [_idea(ROLES[0], 1, "Acoustic monitor"), _idea(ROLES[1], 1, "Strain mesh")],
        "pending_questions": questions,
        "questions_enabled": True,
        "prior_idea_texts": ["Old proposal: text"],
        "gate_flags": {},
        "discards": [],
        "report": None,
        "revision_round": 0,
    }


def _pool(council: Council) -> list[CandidateIdea]:
    assert council.critic.run.await_args is not None
    return list(council.critic.run.await_args.args[0])


async def test_refine_targets_every_ideator_for_clarify_and_the_owner_for_unlock() -> None:
    clarify = _council(IdeaRouter())
    await clarify.graph.run_second_half(_mid_state([_record()]), _ANSWER)
    unlock = _council(IdeaRouter())
    await unlock.graph.run_second_half(_mid_state([_record("unlock", "idea_ideator_2-1")]), _ANSWER)

    assert [len(clarify.router.named(r, "RefinedCandidateIdeas")) for r in ROLES] == [1, 1]
    assert [len(unlock.router.named(r, "RefinedCandidateIdeas")) for r in ROLES] == [0, 1]
    message = unlock.router.named(ROLES[1], "RefinedCandidateIdeas")[0]["messages"][1]
    assert "  Answer: Sealed packs only" in message["content"]


def _changed(title: str) -> dict[str, Any]:
    return {"ideas": [{"title": title, "description": f"{title} description"}], "new_ideas": []}


def _decision(candidate_id: str, action: str, title: str | None = None) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "action": action,
        "revised_title": title,
        "revised_description": f"{title} description" if title else None,
    }


async def _run(router: IdeaRouter, dedup: ScoreDedup | None = None) -> tuple[Council, Any]:
    council = _council(router, dedup)
    _, discards = await council.graph.run_second_half(_mid_state([_record()]), _ANSWER)
    return council, discards


async def test_only_changed_ideas_go_to_the_novelty_recheck() -> None:
    unchanged = {
        "ideas": [{"title": "Strain mesh", "description": "Strain mesh description"}],
        "new_ideas": [],
    }
    router = IdeaRouter(
        refine={ROLES[0]: _changed("Sealed-pack acoustic monitor"), ROLES[1]: unchanged}
    )

    council, _ = await _run(router)

    assert len(router.named(ROLES[0], "json_object")) == 1
    assert (
        "Sealed-pack acoustic monitor"
        in router.named(ROLES[0], "json_object")[0]["messages"][1]["content"]
    )
    assert router.named(ROLES[1], "json_object") == []


async def test_a_changed_idea_cleared_in_round_one_survives() -> None:
    router = IdeaRouter(refine={ROLES[0]: _changed("Sealed-pack acoustic monitor")})

    council, discards = await _run(router)

    assert "Sealed-pack acoustic monitor" in [c.title for c in _pool(council)]
    assert council.prior_art.received == [["q1", "q2"]]
    assert discards == []


async def test_a_changed_idea_reworked_then_cleared_survives_reworked() -> None:
    router = IdeaRouter(
        refine={ROLES[0]: _changed("Sealed-pack acoustic monitor")},
        decisions={ROLES[0]: [[_decision("idea_ideator_1-1", "modify", "Distinct monitor")], []]},
    )

    council, discards = await _run(router)

    titles = [c.title for c in _pool(council)]
    assert "Distinct monitor" in titles
    assert "Sealed-pack acoustic monitor" not in titles
    assert discards == []


async def test_a_changed_idea_reworked_in_both_rounds_is_discarded() -> None:
    rework = [_decision("idea_ideator_1-1", "modify", "Still close")]
    router = IdeaRouter(
        refine={ROLES[0]: _changed("Sealed-pack acoustic monitor")},
        decisions={ROLES[0]: [rework, rework]},
    )

    council, discards = await _run(router)

    assert "idea_ideator_1-1" not in [c.candidate_id for c in _pool(council)]
    assert [d["reason"] for d in discards] == ["identified (semi-)duplicate during novelty check"]


async def test_a_changed_idea_dropped_in_round_one_is_discarded() -> None:
    router = IdeaRouter(
        refine={ROLES[0]: _changed("Sealed-pack acoustic monitor")},
        decisions={ROLES[0]: [[_decision("idea_ideator_1-1", "drop")]]},
    )

    council, discards = await _run(router)

    assert "idea_ideator_1-1" not in [c.candidate_id for c in _pool(council)]
    assert discards == [
        {
            "title": "Sealed-pack acoustic monitor",
            "description": "Sealed-pack acoustic monitor description",
            "reason": "identified (semi-)duplicate during novelty check",
        }
    ]


def _added(*titles_and_text: tuple[str, str]) -> dict[str, Any]:
    return {
        "ideas": [],
        "new_ideas": [{"title": t, "description": d} for t, d in titles_and_text],
    }


async def test_added_ideas_are_capped_cited_and_rechecked() -> None:
    router = IdeaRouter(
        refine={
            ROLES[0]: _added(
                ("Pack vent sensor", "Uses [Q1] sealed packs"),
                ("Uncited idea", "No answer key here"),
                ("Lid strain gauge", "Per [Q1] the lids flex"),
                ("Third cited", "Also [Q1]"),
            )
        }
    )

    council, _ = await _run(router)

    added = [c for c in _pool(council) if "-a" in c.candidate_id]
    assert [(c.candidate_id, c.title) for c in added] == [
        ("idea_ideator_1-a1", "Pack vent sensor"),
        ("idea_ideator_1-a2", "Lid strain gauge"),
    ]
    listing = router.named(ROLES[0], "json_object")[0]["messages"][1]["content"]
    assert "Pack vent sensor" in listing
    assert "Lid strain gauge" in listing


async def test_an_added_duplicate_of_an_earlier_proposal_is_discarded_unsearched() -> None:
    router = IdeaRouter(refine={ROLES[0]: _added(("Old proposal", "Repeats [Q1] old work"))})

    council, discards = await _run(router, ScoreDedup({"Old proposal": 0.95}))

    assert "Old proposal" not in [c.title for c in _pool(council)]
    assert discards == [
        {
            "title": "Old proposal",
            "description": "Repeats [Q1] old work",
            "reason": "near-duplicate of a previous run's output",
        }
    ]
    assert router.named(ROLES[0], "json_object") == []
    assert council.prior_art.received == []


async def test_an_added_near_match_stays_and_the_critic_sees_its_flag() -> None:
    router = IdeaRouter(refine={ROLES[0]: _added(("Close idea", "Per [Q1] close to old work"))})

    council, _ = await _run(router, ScoreDedup({"Close idea": 0.90}))

    assert "Close idea" in [c.title for c in _pool(council)]
    assert council.critic.run.await_args is not None
    evidence = council.critic.run.await_args.kwargs["evidence"]
    assert "idea_ideator_1-a1: resembles prior work (score 0.90): prior output" in evidence


async def test_answers_reach_the_ideation_revision_and_synthesiser() -> None:
    council = _council(IdeaRouter())
    rounds = {"n": 0}

    def delegate_once(candidates: list[CandidateLike], *_a: Any, **_kw: Any) -> CriticReport:
        rounds["n"] += 1
        if rounds["n"] > 1:
            return _keep_all(candidates)
        first = candidates[0].candidate_id
        return CriticReport(
            assessments=[
                CriticAssessment(
                    candidate_id=first,
                    verdict="delegate_back",
                    scores={"specificity": 4},
                    feedback_for_originator="Name the sensor",
                )
            ],
            ranking=[first],
        )

    council.critic.run.side_effect = delegate_once

    await council.graph.run_second_half(_mid_state([_record()]), _ANSWER)

    revision = council.router.named(ROLES[0], "RevisedCandidateIdeas")
    assert len(revision) == 1
    assert "- [Q1] Question: Which packs?" in revision[0]["messages"][1]["content"]
    assert council.synthesiser.run.await_args is not None
    assert "- [Q1] Question: Which packs?" in council.synthesiser.run.await_args.args[2]
