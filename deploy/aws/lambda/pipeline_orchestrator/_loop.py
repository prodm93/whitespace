"""Decision step and result helpers for the SaaS durable orchestrator.

These functions are pure enough to unit-test independently of the SDK.
"""

from __future__ import annotations

from typing import Any

from _actions import _ensure_init, _get_pipeline

from whitespace.agents._orchestrator_tool_defs import TOOL_DEFINITIONS


async def _decide(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Call the model for one orchestrator turn; return the decision."""
    await _ensure_init()
    pipeline = _get_pipeline()
    resp = await pipeline.router.call(
        role="orchestrator",
        messages=messages,
        temperature=0.2,
        tools=TOOL_DEFINITIONS,
    )
    tool_calls = resp.get("tool_calls") or []
    if not tool_calls:
        return {"type": "stop", "content": resp.get("content", "")}
    return {
        "type": "tool_call",
        "content": resp.get("content", ""),
        "tool_calls": tool_calls,
    }


def _compute_status(session: dict[str, Any]) -> str:
    needs = session.get("needs", [])
    return (
        f"profile: {'ready' if session.get('profile') else 'MISSING'}\n"
        f"profile paths staged: {len(session.get('profile_paths', []))}\n"
        f"domain: {session.get('domain') or 'not staged'}\n"
        f"keep_findings: {session.get('keep_findings', False)}\n"
        f"domain docs staged: {len(session.get('doc_paths', []))}\n"
        f"gap results: {[n['title'] for n in needs] or 'none yet'}\n"
        f"user-selected gaps: {session.get('user_selected_titles') or 'none'}\n"
        f"proposals: {len(session.get('proposals', []))}"
    )


def _compute_final_result(session: dict[str, Any]) -> dict[str, Any]:
    proposals = session.get("proposals", [])
    needs = session.get("needs", [])
    blocked_reason = session.get("blocked_reason")
    if proposals:
        status = "done"
    elif blocked_reason:
        status = "blocked"
    elif needs:
        status = "awaiting_selection"
    else:
        status = "done"
    return {
        "needs": needs,
        "proposals": proposals,
        "status": status,
        "reason": blocked_reason,
    }
