"""SaaS analysis pipeline as a Lambda durable function.

One durable execution per orchestrate request; no wait_for_callback for
gap selection. Request 1 runs analysis and ends with awaiting_selection
(results persisted by save_gap_run). Request 2 rehydrates the latest
gap run and ideates. Each LLM decision is a named decide-N step
(replay-compliance rule); side-effectful actions are separate steps;
session state accumulates from step return values only.

Invocation: POST /api/orchestrate -> orchestrate_enqueue -> SQS
orchestrate queue -> durable_dispatcher (async invoke) -> this function.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from _actions import (
    _extract_profile_action,
    _gap_analysis_action,
    _ideation_action,
    _query_action,
    _rehydrate,
)
from _job_state import _increment_run_count, _publish, _set_status
from _loop import _compute_final_result, _compute_status, _decide
from aws_durable_execution_sdk import DurableContext, durable_execution

from whitespace.agents.orchestrator_agent import _SYSTEM_PROMPT

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_MAX_TOOL_CALLS = 12


@durable_execution
def handler(event: dict, context: DurableContext) -> dict:
    job_id: str = event["job_id"]
    payload: dict[str, Any] = event.get("payload", {})
    intent: str = payload.get("intent", "")
    user_id: str = payload.get("user_id", "")
    user_selected_titles: list[str] = list(payload.get("selected_titles", []))
    fresh_start: bool = bool(payload.get("fresh_start", False))

    try:
        context.step(lambda: _set_status(job_id, "running"), name="status_running")

        prior: dict[str, Any] = context.step(
            lambda: asyncio.run(_rehydrate(payload)),
            name="rehydrate_session",
        )

        session: dict[str, Any] = {
            "profile": prior.get("profile"),
            "profile_paths": list(payload.get("profile_paths", [])),
            "domain": prior.get("domain", "") or payload.get("domain", ""),
            "doc_paths": list(payload.get("doc_paths", [])),
            "keep_findings": bool(payload.get("keep_findings", False)),
            "needs": list(prior.get("needs", [])),
            "gap_run_id": prior.get("gap_run_id", ""),
            "user_selected_titles": user_selected_titles,
            "proposals": [],
            "blocked_reason": None,
        }
        gap_analysis_ran = False
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"## USER INTENT\n\n{intent}"},
        ]

        for i in range(_MAX_TOOL_CALLS):
            msgs = list(messages)
            decision: dict[str, Any] = context.step(
                (lambda ms=msgs: asyncio.run(_decide(ms))),
                name=f"decide-{i}",
            )
            if decision["type"] == "stop":
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": decision.get("content", ""),
                    "tool_calls": decision["tool_calls"],
                }
            )

            for call in decision["tool_calls"]:
                tool_name: str = call["name"]
                tool_args: dict[str, Any] = call.get("arguments", {})
                tool_call_id: str = call["id"]

                if tool_name == "get_status":
                    tool_result: str = _compute_status(session)

                elif tool_name == "stage":
                    domain = str(tool_args.get("domain", ""))
                    if not domain:
                        tool_result = "domain is required."
                    else:
                        session["domain"] = domain
                        session["keep_findings"] = bool(tool_args.get("keep_findings", False))
                        session["blocked_reason"] = None
                        tool_result = (
                            f"Staged: domain={domain!r}, keep_findings={session['keep_findings']}."
                        )

                elif tool_name == "extract_profile":
                    s_snap = dict(session)
                    action: dict[str, Any] = context.step(
                        (lambda s=s_snap: asyncio.run(_extract_profile_action(s))),
                        name="extract_profile",
                    )
                    session.update(action["session_updates"])
                    tool_result = action["summary"]

                elif tool_name == "run_gap_analysis":
                    if gap_analysis_ran:
                        n = session.get("needs", [])
                        tool_result = (
                            f"Gap analysis already ran this job. "
                            f"{len(n)} gaps: {'; '.join(x['title'] for x in n)}"
                        )
                    else:
                        s_snap = dict(session)
                        action = context.step(
                            (
                                lambda s=s_snap, jid=job_id, fs=fresh_start: asyncio.run(
                                    _gap_analysis_action(jid, s, fs)
                                )
                            ),
                            name="gap_analysis",
                        )
                        gap_analysis_ran = True
                        session.update(action["session_updates"])
                        if not action["session_updates"].get("blocked_reason") and user_id:
                            context.step(
                                (lambda uid=user_id: _increment_run_count(uid)),
                                name="increment_run_count",
                            )
                        tool_result = action["summary"]

                elif tool_name == "run_ideation":
                    s_snap = dict(session)
                    a_snap = dict(tool_args)
                    action = context.step(
                        (
                            lambda s=s_snap, a=a_snap, jid=job_id, fs=fresh_start: asyncio.run(
                                _ideation_action(jid, s, a, fs)
                            )
                        ),
                        name="ideation",
                    )
                    session.update(action["session_updates"])
                    tool_result = action["summary"]

                elif tool_name == "query_knowledge_graph":
                    q = str(tool_args.get("question", ""))
                    action = context.step(
                        (lambda question=q: asyncio.run(_query_action(question))),
                        name=f"query-{i}",
                    )
                    tool_result = action

                else:
                    tool_result = f"Unknown tool: {tool_name}"

                messages.append(
                    {"role": "tool", "tool_call_id": tool_call_id, "content": tool_result}
                )

        result = _compute_final_result(session)
        context.step(lambda: _publish(job_id, result), name="publish_results")
        return result

    except Exception as exc:
        context.step(
            (lambda e=exc: _set_status(job_id, "failed", error=str(e))),
            name="status_failed",
        )
        raise
