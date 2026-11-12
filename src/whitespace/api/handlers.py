"""Job handlers registered on the local queue in BYOK mode."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from whitespace.schemas.question import UserAnswer

if TYPE_CHECKING:
    from whitespace.orchestration.pipeline import Pipeline
    from whitespace.queue.local_queue import LocalAsyncQueue

logger = logging.getLogger(__name__)

KEYS_NOT_SAVED = "Your new keys could not be saved. Enter them again."


def register_handlers(queue: LocalAsyncQueue) -> None:
    from whitespace.api.state import CredentialsNotSet, app_state

    async def handle_ingest(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        profile_paths: list[str] = payload.get("profile_paths", [])
        domain_paths: list[str] = payload.get("domain_paths", [])

        app_state.set_profile_paths(profile_paths)

        all_paths = profile_paths + domain_paths
        domain = ", ".join(payload.get("domain_keywords", []))
        app_state.set_pending_ingest(
            domain,
            all_paths,
            bool(payload.get("keep_findings", False)),
        )
        return {"documents_staged": len(all_paths)}

    async def handle_orchestrate(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if app_state.credentials_error() is not None:
            return {
                "status": "blocked",
                "reason": KEYS_NOT_SAVED,
                "needs": [],
                "proposals": [],
                "questions": [],
                "stage": "",
            }
        try:
            async with app_state.use_pipeline() as pipeline:
                return await _run_orchestrator(job_id, payload, pipeline)
        except CredentialsNotSet as exc:
            raise RuntimeError(str(exc)) from exc

    queue.register_handler("ingest", handle_ingest)
    queue.register_handler("orchestrate", handle_orchestrate)


def answers_from_payload(raw: list[dict[str, Any]] | None) -> list[UserAnswer] | None:
    """The submitted answers; ``None`` means no submission. A blank answer is skipped."""
    if raw is None:
        return None
    answers: list[UserAnswer] = []
    for entry in raw:
        answer = str(entry.get("answer") or "")
        if entry.get("skipped") or not answer.strip():
            answers.append(UserAnswer(question_id=str(entry["question_id"]), status="skipped"))
        else:
            answers.append(
                UserAnswer(question_id=str(entry["question_id"]), status="answered", answer=answer)
            )
    return answers


async def _run_orchestrator(
    job_id: str, payload: dict[str, Any], pipeline: Pipeline
) -> dict[str, Any]:
    from whitespace.agents._orchestrator_actions import OrchestratorActions
    from whitespace.agents._orchestrator_session import AnalysisSession
    from whitespace.agents.orchestrator_agent import OrchestratorAgent
    from whitespace.api.state import ProfileNotReady, app_state

    try:
        profile = app_state.get_profile()
    except ProfileNotReady:
        profile = None
    domain, doc_paths, keep_findings = app_state.get_pending_ingest()
    store = app_state.get_store()
    gap_run = await store.get_latest_gap_run() if store is not None else None
    session = AnalysisSession(
        profile=profile,
        profile_paths=app_state.get_profile_paths(),
        domain=domain,
        doc_paths=doc_paths,
        keep_findings=keep_findings,
        run_id=job_id,
        gap_run_id=gap_run.run_id if gap_run is not None else "",
        fresh_start=bool(payload.get("fresh_start", False)),
        needs=list(gap_run.needs) if gap_run is not None else [],
        user_selected_titles=list(payload.get("selected_titles", [])),
        ask_questions=payload.get("ask_questions") is not False,
        question_answers=answers_from_payload(payload.get("question_answers")),
    )
    result = await OrchestratorAgent(pipeline.router).run(
        payload.get("intent", ""),
        OrchestratorActions(pipeline, session, state_writer=app_state),
    )
    return {
        "needs": [n.model_dump() for n in result.needs],
        "proposals": [p.model_dump() for p in result.proposals],
        "status": result.status,
        "reason": result.reason,
        "questions": [
            {
                "question_id": q.question_id,
                "question": q.question,
                "hypothesis": q.hypothesis,
                "rationale": q.rationale,
            }
            for q in result.questions
        ],
        "stage": result.stage,
    }
