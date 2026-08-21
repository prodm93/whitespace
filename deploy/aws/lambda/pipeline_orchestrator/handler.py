"""SaaS analysis pipeline as a Lambda durable function.

Request 1 runs analysis, persists gaps. Request 2 rehydrates and ideates.
LLM decisions are named steps (replay-compliance); session state
accumulates from step return values only.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from _actions import _rehydrate
from _dispatch import dispatch_tool
from _job_state import _publish, _set_status
from _loop import _compute_final_result, _decide
from _reservation_ops import _cleanup_reservation, _release_reservation, _validate_usage_config
from _reservation_state import (
    _USER_FACING_ERROR,
    ReservationMode,
    ReservationStateError,
    _expire_reservation_lease,
    _validate_and_start,
)
from aws_durable_execution_sdk_python import DurableContext, durable_execution

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

    reservation_done = False
    ownership_verified = False
    owned_expired = False
    reservation_mode: ReservationMode | None = None
    try:
        if not user_id:
            raise ReservationStateError(_USER_FACING_ERROR)

        start_outcome = context.step(
            (lambda _, jid=job_id, uid=user_id: _validate_and_start(jid, uid)),
            name="validate_and_start",
        )
        ownership_verified = True
        if start_outcome == "owned_expired":
            owned_expired = True
            raise ReservationStateError(_USER_FACING_ERROR)
        reservation_mode = start_outcome

        if reservation_mode == "required":
            context.step(lambda _: _validate_usage_config(), name="validate_usage_config")

        prior: dict[str, Any] = context.step(
            lambda _: asyncio.run(_rehydrate(payload)),
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
                (lambda _, ms=msgs: asyncio.run(_decide(ms))),
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
                tr = dispatch_tool(
                    call,
                    session,
                    context,
                    job_id,
                    user_id,
                    fresh_start,
                    reservation_mode,
                    gap_analysis_ran,
                    i,
                )
                if tr.gap_ran:
                    gap_analysis_ran = True
                if tr.reservation_done:
                    reservation_done = True
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": tr.result})

        if reservation_mode == "required" and not reservation_done and user_id:
            context.step(
                (lambda _, uid=user_id, jid=job_id: _release_reservation(uid, jid, "claimed")),
                name="release_unused_reservation",
            )

        result = _compute_final_result(session)
        context.step(lambda _: _publish(job_id, result), name="publish_results")
        return result

    except ReservationStateError as rse:
        if ownership_verified:
            if owned_expired:
                try:
                    context.step(
                        (lambda _, uid=user_id, jid=job_id: _cleanup_reservation(uid, jid)),
                        name="cleanup_expired_reservation",
                    )
                except Exception as cleanup_exc:
                    logger.error(
                        "Expired reservation cleanup failed for %s: %s", job_id, cleanup_exc
                    )
            elif reservation_mode == "required" and not reservation_done:
                try:
                    context.step(
                        (lambda _, jid=job_id, uid=user_id: _expire_reservation_lease(jid, uid)),
                        name="expire_lease",
                    )
                except Exception:
                    logger.error("Failed to expire lease for %s", job_id)
            try:
                context.step(
                    (lambda _, e=rse: _set_status(job_id, "failed", error=str(e))),
                    name="status_failed",
                )
            except Exception:
                logger.error("Failed to write failed status for %s", job_id)
        raise

    except Exception as exc:
        if ownership_verified and not reservation_done:
            try:
                context.step(
                    (lambda _, uid=user_id, jid=job_id: _cleanup_reservation(uid, jid)),
                    name="cleanup_reservation",
                )
            except Exception as cleanup_exc:
                logger.error("Reservation cleanup failed for %s: %s", job_id, cleanup_exc)
                if reservation_mode == "required":
                    try:
                        context.step(
                            (
                                lambda _, jid=job_id, uid=user_id: _expire_reservation_lease(
                                    jid, uid
                                )
                            ),
                            name="expire_lease",
                        )
                    except Exception:
                        logger.error("Failed to expire lease for %s", job_id)
        if ownership_verified:
            try:
                context.step(
                    (lambda _, e=exc: _set_status(job_id, "failed", error=str(e))),
                    name="status_failed",
                )
            except Exception:
                logger.error("Failed to write failed status for %s", job_id)
        raise
