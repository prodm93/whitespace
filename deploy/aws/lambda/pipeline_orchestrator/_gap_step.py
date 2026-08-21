"""Gap analysis step with reservation lifecycle for the durable pipeline."""

from __future__ import annotations

import asyncio
from typing import Any

from _actions import _gap_analysis_action
from _reservation_ops import _convert_reservation, _release_reservation
from _reservation_state import ReservationMode
from aws_durable_execution_sdk_python import DurableContext


def _handle_gap_analysis(
    context: DurableContext,
    session: dict[str, Any],
    job_id: str,
    user_id: str,
    fresh_start: bool,
    reservation_mode: ReservationMode,
) -> dict[str, Any]:
    """Run gap analysis with reservation lifecycle.

    Mutates *session* in place on success.
    """
    reservation_required = reservation_mode == "required"

    s_snap = dict(session)
    action: dict[str, Any] = context.step(
        (
            lambda _, s=s_snap, jid=job_id, fs=fresh_start: asyncio.run(
                _gap_analysis_action(jid, s, fs)
            )
        ),
        name="gap_analysis",
    )
    session.update(action["session_updates"])

    if not reservation_required:
        return {
            "summary": action["summary"],
            "ran": True,
            "reservation_done": False,
        }

    if action["session_updates"].get("blocked_reason"):
        context.step(
            (lambda _, uid=user_id, jid=job_id: _release_reservation(uid, jid, "claimed")),
            name="release_reservation_blocked",
        )
    else:
        context.step(
            (lambda _, uid=user_id, jid=job_id: _convert_reservation(uid, jid)),
            name="convert_reservation",
        )

    return {
        "summary": action["summary"],
        "ran": True,
        "reservation_done": True,
    }
