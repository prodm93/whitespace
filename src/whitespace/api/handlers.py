"""BYOK job handlers — extracted from the app factory for the 200-line limit."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from whitespace.queue.local_queue import LocalAsyncQueue

logger = logging.getLogger(__name__)


def register_handlers(queue: LocalAsyncQueue) -> None:
    from typing import Any

    from whitespace.api.state import (
        CredentialsNotSet,
        ProfileNotReady,
        app_state,
    )

    async def handle_ingest(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            pipeline = await app_state.get_pipeline()
        except CredentialsNotSet as exc:
            raise RuntimeError(str(exc)) from exc

        profile_paths: list[str] = payload.get("profile_paths", [])
        domain_paths: list[str] = payload.get("domain_paths", [])

        if profile_paths:
            profile = await pipeline.extract_profile(profile_paths)
            app_state.set_profile(profile)

        # Documents are staged here; the gap run ingests them together
        # with the research findings in one graph build.
        all_paths = profile_paths + domain_paths
        domain = ", ".join(payload.get("domain_keywords", []))
        app_state.set_pending_ingest(
            domain,
            all_paths,
            bool(payload.get("keep_findings", False)),
        )
        return {"documents_staged": len(all_paths)}

    async def handle_gaps(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            pipeline = await app_state.get_pipeline()
        except CredentialsNotSet as exc:
            raise RuntimeError(str(exc)) from exc
        try:
            profile = app_state.get_profile()
        except ProfileNotReady as exc:
            raise RuntimeError(str(exc)) from exc
        domain, doc_paths, keep_findings = app_state.get_pending_ingest()
        needs = await pipeline.analyse_gaps(
            profile,
            domain,
            doc_paths,
            keep_findings=keep_findings,
            run_id=job_id,
            fresh_start=bool(payload.get("fresh_start", False)),
        )
        return {"needs": [n.model_dump() for n in needs]}

    async def handle_ideation(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            pipeline = await app_state.get_pipeline()
        except CredentialsNotSet as exc:
            raise RuntimeError(str(exc)) from exc
        try:
            profile = app_state.get_profile()
        except ProfileNotReady as exc:
            raise RuntimeError(str(exc)) from exc
        store = app_state.get_store()
        gap_run = await store.get_latest_gap_run() if store is not None else None
        if gap_run is None:
            raise RuntimeError("No gap analysis results found; run gap analysis first")
        titles = set(payload["selected_needs"])
        selected = [n for n in gap_run.needs if n.title in titles]
        if not selected:
            raise RuntimeError("Selected titles do not match the latest gap results")
        proposals = await pipeline.ideate(
            selected,
            profile,
            run_id=job_id,
            gap_run_id=gap_run.run_id,
            fresh_start=bool(payload.get("fresh_start", False)),
        )
        return {"proposals": [p.model_dump() for p in proposals]}

    async def handle_orchestrate(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from whitespace.agents._orchestrator_actions import AnalysisSession, OrchestratorActions
        from whitespace.agents.orchestrator_agent import OrchestratorAgent

        try:
            pipeline = await app_state.get_pipeline()
        except CredentialsNotSet as exc:
            raise RuntimeError(str(exc)) from exc
        try:
            profile = app_state.get_profile()
        except ProfileNotReady:
            profile = None
        domain, doc_paths, keep_findings = app_state.get_pending_ingest()
        session = AnalysisSession(
            profile=profile,
            domain=domain,
            doc_paths=doc_paths,
            keep_findings=keep_findings,
            run_id=job_id,
        )
        result = await OrchestratorAgent(pipeline.router).run(
            payload.get("intent", ""),
            OrchestratorActions(pipeline, session),
        )
        return {
            "narrative": result.narrative,
            "needs": [n.model_dump() for n in result.needs],
            "proposals": [p.model_dump() for p in result.proposals],
        }

    queue.register_handler("ingest", handle_ingest)
    queue.register_handler("orchestrate", handle_orchestrate)
    queue.register_handler("gap_analysis", handle_gaps)
    queue.register_handler("ideation", handle_ideation)
