"""Tool dispatch for the durable pipeline handler."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from _actions import (
    _extract_profile_action,
    _ideation_action,
    _query_action,
)
from _gap_step import _handle_gap_analysis
from _loop import _compute_status
from _reservation_state import ReservationMode
from aws_durable_execution_sdk_python import DurableContext


@dataclass
class ToolResult:
    """Return value from a single tool dispatch."""

    result: str
    gap_ran: bool = False
    reservation_done: bool = False


def dispatch_tool(
    call: dict[str, Any],
    session: dict[str, Any],
    context: DurableContext,
    job_id: str,
    user_id: str,
    fresh_start: bool,
    reservation_mode: ReservationMode | None,
    gap_analysis_ran: bool,
    loop_index: int,
) -> ToolResult:
    """Route a single tool call to its action and return the result."""
    name: str = call["name"]
    args: dict[str, Any] = call.get("arguments", {})

    if name == "get_status":
        return ToolResult(result=_compute_status(session))

    if name == "stage":
        return _handle_stage(session, args)

    if name == "extract_profile":
        return _handle_extract_profile(session, context)

    if name == "run_gap_analysis":
        return _handle_gap(
            session,
            context,
            job_id,
            user_id,
            fresh_start,
            reservation_mode,
            gap_analysis_ran,
        )

    if name == "run_ideation":
        return _handle_ideation(session, context, args, job_id, fresh_start)

    if name == "query_knowledge_graph":
        q = str(args.get("question", ""))
        r = context.step(
            (lambda _, question=q: asyncio.run(_query_action(question))),
            name=f"query-{loop_index}",
        )
        return ToolResult(result=r)

    return ToolResult(result=f"Unknown tool: {name}")


def _handle_stage(session: dict[str, Any], args: dict[str, Any]) -> ToolResult:
    domain = str(args.get("domain", ""))
    if not domain:
        return ToolResult(result="domain is required.")
    session["domain"] = domain
    session["keep_findings"] = bool(args.get("keep_findings", False))
    session["blocked_reason"] = None
    return ToolResult(
        result=f"Staged: domain={domain!r}, keep_findings={session['keep_findings']}.",
    )


def _handle_extract_profile(
    session: dict[str, Any],
    context: DurableContext,
) -> ToolResult:
    s_snap = dict(session)
    action: dict[str, Any] = context.step(
        (lambda _, s=s_snap: asyncio.run(_extract_profile_action(s))),
        name="extract_profile",
    )
    session.update(action["session_updates"])
    return ToolResult(result=action["summary"])


def _handle_gap(
    session: dict[str, Any],
    context: DurableContext,
    job_id: str,
    user_id: str,
    fresh_start: bool,
    reservation_mode: ReservationMode | None,
    gap_analysis_ran: bool,
) -> ToolResult:
    if gap_analysis_ran:
        n = session.get("needs", [])
        return ToolResult(
            result=(
                f"Gap analysis already ran this job. "
                f"{len(n)} gaps: {'; '.join(x['title'] for x in n)}"
            ),
        )
    gap_result = _handle_gap_analysis(
        context,
        session,
        job_id,
        user_id,
        fresh_start,
        reservation_mode,
    )
    return ToolResult(
        result=gap_result["summary"],
        gap_ran=gap_result["ran"],
        reservation_done=bool(gap_result.get("reservation_done")),
    )


def _handle_ideation(
    session: dict[str, Any],
    context: DurableContext,
    args: dict[str, Any],
    job_id: str,
    fresh_start: bool,
) -> ToolResult:
    s_snap = dict(session)
    a_snap = dict(args)
    action: dict[str, Any] = context.step(
        (
            lambda _, s=s_snap, a=a_snap, jid=job_id, fs=fresh_start: asyncio.run(
                _ideation_action(jid, s, a, fs)
            )
        ),
        name="ideation",
    )
    session.update(action["session_updates"])
    return ToolResult(result=action["summary"])
