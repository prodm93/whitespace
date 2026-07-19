"""Pipeline action steps for the SaaS durable orchestrator.

Each public function is called from inside a durable step; the caller
wraps it in asyncio.run(). Every function either reads/writes external
state (pipeline, store, S3) or computes the status and result shape.
Session state is returned as a dict and applied by the handler body.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from whitespace.orchestration.pipeline import Pipeline
    from whitespace.store.base import SessionStore

logger = logging.getLogger(__name__)

_pipeline: Pipeline | None = None
_session_store: SessionStore | None = None
_UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")
_AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")


def _build_session_store(config: Any) -> SessionStore:
    if config.sessions_table:
        from whitespace.store.dynamo_store import DynamoSessionStore

        return DynamoSessionStore(config.sessions_table, config.aws_region)
    logger.warning("SESSIONS_TABLE not set; session persistence disabled")
    from whitespace.store.noop_store import NoopSessionStore

    return NoopSessionStore()


async def _ensure_init() -> None:
    global _pipeline, _session_store
    if _pipeline is None:
        from whitespace.config import Config
        from whitespace.orchestration.pipeline import Pipeline

        config = Config()
        _session_store = _build_session_store(config)
        _pipeline = Pipeline.from_config(config, session_store=_session_store)
        await _pipeline.initialise()


def _get_pipeline() -> Pipeline:
    assert _pipeline is not None, "_ensure_init() must be awaited first"
    return _pipeline


def _get_store() -> SessionStore | None:
    return _session_store


async def _localise_paths(paths: list[str]) -> list[str]:
    """Download S3 keys from the uploads bucket to /tmp; return local paths."""
    import hashlib

    import boto3

    s3 = boto3.client("s3", region_name=_AWS_REGION)
    local: list[str] = []
    os.makedirs("/tmp/whitespace", exist_ok=True)
    for path in paths:
        if path.startswith("/"):
            local.append(path)
            continue
        digest = hashlib.md5(path.encode()).hexdigest()[:10]
        fname = f"{digest}_{os.path.basename(path)}"
        local_path = f"/tmp/whitespace/{fname}"
        if not os.path.exists(local_path):
            await asyncio.to_thread(s3.download_file, _UPLOADS_BUCKET, path, local_path)
        local.append(local_path)
    return local


async def _rehydrate(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the latest persisted gap run for request-2 session priming."""
    await _ensure_init()
    store = _get_store()
    if store is None:
        return {"profile": None, "domain": "", "needs": [], "gap_run_id": ""}
    gap_run = await store.get_latest_gap_run()
    if gap_run is None:
        return {"profile": None, "domain": "", "needs": [], "gap_run_id": ""}
    return {
        "profile": None,
        "domain": gap_run.domain or "",
        "needs": [n.model_dump() for n in gap_run.needs],
        "gap_run_id": gap_run.run_id,
    }


async def _extract_profile_action(session_snap: dict[str, Any]) -> dict[str, Any]:
    await _ensure_init()
    paths = session_snap.get("profile_paths", [])
    if not paths:
        msg = "No profile paths staged. Upload profile documents first."
        return {"summary": msg, "session_updates": {"blocked_reason": msg}}
    local_paths = await _localise_paths(paths)
    pipeline = _get_pipeline()
    profile = await pipeline.extract_profile(local_paths)
    return {
        "summary": (
            f"Profile extracted: {len(profile.hard_skills)} hard skills, "
            f"{len(profile.domain_knowledge)} domain areas."
        ),
        "session_updates": {"profile": profile.model_dump(), "blocked_reason": None},
    }


async def _gap_analysis_action(
    job_id: str,
    session_snap: dict[str, Any],
    fresh_start: bool,
) -> dict[str, Any]:
    await _ensure_init()
    profile_dict = session_snap.get("profile")
    if profile_dict is None:
        msg = "Cannot run: no profile. Call extract_profile first."
        return {"summary": msg, "session_updates": {"blocked_reason": msg}}
    domain = session_snap.get("domain", "")
    if not domain:
        msg = "Cannot run: no domain. Call stage(domain=...) first."
        return {"summary": msg, "session_updates": {"blocked_reason": msg}}
    from whitespace.schemas.profile import ProfessionalProfile

    local_docs = await _localise_paths(session_snap.get("doc_paths", []))
    pipeline = _get_pipeline()
    needs = await pipeline.analyse_gaps(
        ProfessionalProfile.model_validate(profile_dict),
        domain,
        local_docs,
        keep_findings=bool(session_snap.get("keep_findings", False)),
        run_id=job_id,
        fresh_start=fresh_start,
    )
    titles = "; ".join(n.title for n in needs)
    return {
        "summary": f"Gap analysis complete. {len(needs)} gaps found: {titles}",
        "session_updates": {
            "needs": [n.model_dump() for n in needs],
            "gap_run_id": job_id,
            "blocked_reason": None,
        },
    }


async def _ideation_action(
    job_id: str,
    session_snap: dict[str, Any],
    tool_args: dict[str, Any],
    fresh_start: bool,
) -> dict[str, Any]:
    await _ensure_init()
    user_selected = set(session_snap.get("user_selected_titles", []))
    if not user_selected:
        return {
            "summary": (
                "Cannot run: gap selection must come from the user's confirmed "
                "checkbox state. No sidecar was provided."
            ),
            "session_updates": {},
        }
    requested = [t for t in list(tool_args.get("selected_titles", [])) if t in user_selected]
    if not requested:
        return {
            "summary": (
                f"None of the requested titles are in the user's confirmed "
                f"selection {sorted(user_selected)}. Check get_status."
            ),
            "session_updates": {},
        }
    profile_dict = session_snap.get("profile")
    if profile_dict is None:
        msg = "Cannot run: no profile."
        return {"summary": msg, "session_updates": {"blocked_reason": msg}}
    needs_dicts = session_snap.get("needs", [])
    if not needs_dicts:
        msg = "Cannot run: no gap results yet. Run gap analysis first."
        return {"summary": msg, "session_updates": {"blocked_reason": msg}}
    from whitespace.schemas.gap import UnmetNeed
    from whitespace.schemas.profile import ProfessionalProfile

    chosen = [UnmetNeed.model_validate(n) for n in needs_dicts if n.get("title") in set(requested)]
    if not chosen:
        return {
            "summary": "None of the allowed titles match gap results. Check get_status.",
            "session_updates": {},
        }
    pipeline = _get_pipeline()
    proposals = await pipeline.ideate(
        chosen,
        ProfessionalProfile.model_validate(profile_dict),
        gap_run_id=session_snap.get("gap_run_id", ""),
        fresh_start=fresh_start,
    )
    titles = "; ".join(p.title for p in proposals)
    return {
        "summary": f"Ideation complete. {len(proposals)} proposals: {titles}",
        "session_updates": {
            "proposals": [p.model_dump() for p in proposals],
            "blocked_reason": None,
        },
    }


async def _query_action(question: str) -> str:
    await _ensure_init()
    if not question:
        return "No question given."
    return await _get_pipeline().query(question)
