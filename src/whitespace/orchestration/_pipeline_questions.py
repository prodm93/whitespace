"""Pipeline entry points for runs that may pause to ask the user questions (BYOK)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from whitespace.orchestration._gap_council_state import build_initial_gap_state, dump_mid_state
from whitespace.orchestration._ideation_council_state import (
    build_initial_ideation_state,
    dump_ideation_state,
)
from whitespace.orchestration._memory import load_gap_memory, load_ideation_prior_texts
from whitespace.orchestration._question_types import (
    NoPendingPause,
    PausedForQuestions,
    ResumedRun,
)
from whitespace.orchestration._research_stage import RunMemory
from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import QuestionRecord, UserAnswer
from whitespace.store.base import PendingPause

if TYPE_CHECKING:
    from whitespace.orchestration._question_runs import QuestionRuns
    from whitespace.store.base import SessionStore
    from whitespace.tools.dedup import SemanticDeduplicator


class PipelineQuestionsMixin:
    """Question-enabled runs; without ``QuestionRuns`` they fall back to the plain runs."""

    _store: SessionStore | None
    _dedup: SemanticDeduplicator
    _question_runs: QuestionRuns | None

    if TYPE_CHECKING:

        async def analyse_gaps(
            self,
            profile: ProfessionalProfile,
            domain: str,
            doc_paths: list[str] | None = None,
            *,
            keep_findings: bool = False,
            run_id: str | None = None,
            fresh_start: bool = False,
        ) -> list[UnmetNeed]: ...

        async def ideate(
            self,
            selected_needs: list[UnmetNeed],
            profile: ProfessionalProfile,
            *,
            run_id: str | None = None,
            gap_run_id: str = "",
            fresh_start: bool = False,
        ) -> list[IdeationProposal]: ...

        async def _ideation_context(self, fresh_start: bool) -> str: ...

    async def analyse_gaps_with_questions(
        self,
        profile: ProfessionalProfile,
        domain: str,
        doc_paths: list[str] | None = None,
        *,
        keep_findings: bool = False,
        run_id: str | None = None,
        fresh_start: bool = False,
    ) -> list[UnmetNeed] | PausedForQuestions:
        """A gap analysis that may pause after its first half to ask the user."""
        run_id = run_id or str(uuid.uuid4())
        if self._question_runs is None:
            return await self.analyse_gaps(
                profile,
                domain,
                doc_paths,
                keep_findings=keep_findings,
                run_id=run_id,
                fresh_start=fresh_start,
            )
        if fresh_start:
            memory = RunMemory()
        else:
            memory = await load_gap_memory(self._store, domain, self._dedup)
        initial = build_initial_gap_state(
            profile,
            domain,
            doc_paths,
            keep_findings=keep_findings,
            run_id=run_id,
            run_memory=memory,
            questions_enabled=True,
        )
        outcome = await self._question_runs.start("gap", run_id, dump_mid_state(initial))
        if outcome.questions:
            return PausedForQuestions(
                "gap", [QuestionRecord.model_validate(q) for q in outcome.questions]
            )
        return [UnmetNeed.model_validate(n) for n in (outcome.result or {}).get("needs", [])]

    async def ideate_with_questions(
        self,
        selected_needs: list[UnmetNeed],
        profile: ProfessionalProfile,
        *,
        run_id: str | None = None,
        gap_run_id: str = "",
        fresh_start: bool = False,
        domain: str = "",
    ) -> list[IdeationProposal] | PausedForQuestions:
        """An ideation run that may pause after its novelty check to ask the user."""
        run_id = run_id or str(uuid.uuid4())
        if self._question_runs is None:
            return await self.ideate(
                selected_needs,
                profile,
                run_id=run_id,
                gap_run_id=gap_run_id,
                fresh_start=fresh_start,
            )
        context = await self._ideation_context(fresh_start)
        prior = [] if fresh_start else await load_ideation_prior_texts(self._store)
        initial = build_initial_ideation_state(
            selected_needs,
            profile,
            context,
            run_id=run_id,
            gap_run_id=gap_run_id,
            domain=domain,
            questions_enabled=True,
            prior_idea_texts=prior,
        )
        outcome = await self._question_runs.start("ideation", run_id, dump_ideation_state(initial))
        if outcome.questions:
            return PausedForQuestions(
                "ideation", [QuestionRecord.model_validate(q) for q in outcome.questions]
            )
        proposals = (outcome.result or {}).get("proposals", [])
        return [IdeationProposal.model_validate(p) for p in proposals]

    async def resume_questions(self, submission: list[UserAnswer]) -> ResumedRun:
        """Continue the paused run with the user's answers."""
        if self._question_runs is None:
            raise NoPendingPause("questions are not enabled in this mode")
        return await self._question_runs.resume(submission)

    async def discard_pending_questions(self) -> bool:
        """Drop the paused run, if there is one."""
        if self._question_runs is None:
            return False
        return await self._question_runs.discard_pending()

    async def pending_questions(self) -> PendingPause | None:
        """The paused run's row, if there is one."""
        if self._question_runs is None or self._store is None:
            return None
        return await self._store.get_pending_pause()
