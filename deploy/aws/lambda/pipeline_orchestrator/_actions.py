"""Pipeline action steps for the SaaS durable orchestrator.

Each public function is called from inside a durable step; the caller runs it on the
kept event loop with ``run()``. The pipeline and the store are those of the open run.
Every function either reads/writes external state (pipeline, store, S3) or computes
the status and result shape. Session state is returned as a dict and applied by the
handler body.
"""

from __future__ import annotations

from typing import Any

from _runtime import current_owner, get_pipeline, get_store
from _uploads import localise_paths


async def _rehydrate(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the latest persisted gap run for request-2 session priming.

    The run's stored profile is returned, except when the request stages new profile
    documents: then the profile is ``None`` and the new documents are extracted.
    """
    gap_run = await get_store().get_latest_gap_run()
    if gap_run is None:
        return {"profile": None, "domain": "", "needs": [], "gap_run_id": ""}
    stored = gap_run.profile
    if stored is None or payload.get("profile_paths"):
        profile = None
    else:
        profile = stored.model_dump(mode="json")
    return {
        "profile": profile,
        "domain": gap_run.domain or "",
        "needs": [n.model_dump() for n in gap_run.needs],
        "gap_run_id": gap_run.run_id,
    }


async def _extract_profile_action(session_snap: dict[str, Any]) -> dict[str, Any]:
    paths = session_snap.get("profile_paths", [])
    if not paths:
        msg = "No profile paths staged. Upload profile documents first."
        return {"summary": msg, "session_updates": {"blocked_reason": msg}}
    local_paths = await localise_paths(paths, current_owner())
    pipeline = get_pipeline()
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
    profile_dict = session_snap.get("profile")
    if profile_dict is None:
        msg = "Cannot run: no profile. Call extract_profile first."
        return {"summary": msg, "session_updates": {"blocked_reason": msg}}
    domain = session_snap.get("domain", "")
    if not domain:
        msg = "Cannot run: no domain. Call stage(domain=...) first."
        return {"summary": msg, "session_updates": {"blocked_reason": msg}}
    from whitespace.schemas.profile import ProfessionalProfile

    local_docs = await localise_paths(session_snap.get("doc_paths", []), current_owner())
    pipeline = get_pipeline()
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
    pipeline = get_pipeline()
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
    if not question:
        return "No question given."
    return await get_pipeline().query(question)
