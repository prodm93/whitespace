"""Agentic gate that selects whether and what to ask the user."""

from __future__ import annotations

import json
import logging
from typing import Literal

from whitespace.agents.council._question_gate_context import build_gate_context
from whitespace.agents.council._question_gate_prompt import (
    GATE_RESPONSE_FORMAT,
    SYSTEM_PROMPT,
)
from whitespace.agents.council._question_gate_records import save_gate_records
from whitespace.agents.council._question_gate_selection import (
    SelectedQuestion,
    apply_selection_rails,
    parse_selected_questions,
)
from whitespace.config import Config
from whitespace.models.router import ModelRouter
from whitespace.schemas._question_scoring import EXACT_DUPLICATE_THRESHOLD
from whitespace.schemas.question import GateDecision, ProposedQuestion, QuestionRecord
from whitespace.store.base import SessionStore
from whitespace.tools.dedup import SemanticDeduplicator

logger = logging.getLogger(__name__)

Stage = Literal["gap", "ideation"]


class QuestionGate:
    """Select high-value questions using learned context and hard safety rails."""

    def __init__(
        self,
        config: Config,
        router: ModelRouter,
        dedup: SemanticDeduplicator,
        store: SessionStore,
    ) -> None:
        self._config = config
        self._router = router
        self._dedup = dedup
        self._store = store

    async def judge(
        self,
        proposals: list[ProposedQuestion],
        run_summary: str,
        stage: Stage,
        run_id: str,
        domain: str = "",
    ) -> GateDecision:
        if not proposals:
            return GateDecision(ask=False, questions=[], reasoning="No questions proposed.")

        history = await self._store.list_question_records()
        indexed = {f"P{index}": proposal for index, proposal in enumerate(proposals, 1)}
        eligible, similar = await self._remove_exact_duplicates(indexed, history)
        if not eligible:
            await self._save(proposals, [], stage, run_id, domain)
            return GateDecision(
                ask=False,
                questions=[],
                reasoning="All proposals duplicated answered questions.",
            )

        user_prompt = build_gate_context(eligible, run_summary, stage, run_id, history, similar)
        try:
            response = await self._router.call(
                role="question_gate",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                response_format=GATE_RESPONSE_FORMAT,
            )
            raw = json.loads(response["content"])
            ask = isinstance(raw, dict) and raw.get("ask") is True
            reasoning = raw.get("reasoning") if isinstance(raw, dict) else ""
            if not isinstance(reasoning, str):
                reasoning = ""
            selected = parse_selected_questions(raw, eligible) if ask else []
            selected = apply_selection_rails(selected, raw, eligible) if ask else []
        except Exception:
            logger.exception("QuestionGate: model judgment failed; continuing without questions")
            await self._save(proposals, [], stage, run_id, domain)
            return GateDecision(
                ask=False,
                questions=[],
                reasoning="Question gate unavailable; continued without interruption.",
            )

        records = await self._save(proposals, selected, stage, run_id, domain)
        asked_records = [record for record in records if record.asked]
        return GateDecision(
            ask=bool(asked_records),
            questions=asked_records,
            reasoning=reasoning,
        )

    async def _remove_exact_duplicates(
        self,
        proposals: dict[str, ProposedQuestion],
        history: list[QuestionRecord],
    ) -> tuple[dict[str, ProposedQuestion], list[tuple[str, float, QuestionRecord]]]:
        answered = [record for record in history if record.asked and record.status == "answered"]
        if not answered:
            return proposals, []
        matches = await self._dedup.score_against_with_best(
            [proposal.question for proposal in proposals.values()],
            [record.question for record in answered],
        )
        records_by_text = {record.question: record for record in answered}
        eligible: dict[str, ProposedQuestion] = {}
        similar: list[tuple[str, float, QuestionRecord]] = []
        for (proposal_id, proposal), (score, best_text) in zip(
            proposals.items(), matches, strict=True
        ):
            if score >= EXACT_DUPLICATE_THRESHOLD:
                continue
            eligible[proposal_id] = proposal
            record = records_by_text.get(best_text)
            if record is not None:
                similar.append((proposal_id, score, record))
        return eligible, similar

    async def _save(
        self,
        proposals: list[ProposedQuestion],
        selected: list[SelectedQuestion],
        stage: Stage,
        run_id: str,
        domain: str,
    ) -> list[QuestionRecord]:
        return await save_gate_records(self._store, proposals, selected, stage, run_id, domain)
