"""What the pipeline function records when a job fails: reservation cleanup, then status."""

from __future__ import annotations

import logging
from typing import Any

from _job_state import _set_status
from _reservation_ops import _cleanup_reservation
from _reservation_state import ReservationMode, _expire_reservation_lease

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handle_reservation_error(
    context: Any,
    job_id: str,
    user_id: str,
    error: Exception,
    *,
    ownership_verified: bool,
    owned_expired: bool,
    reservation_mode: ReservationMode | None,
    reservation_done: bool,
) -> None:
    """Release or expire the reservation of a refused job, then write it as failed."""
    if ownership_verified:
        if owned_expired:
            try:
                context.step(
                    (lambda _, uid=user_id, jid=job_id: _cleanup_reservation(uid, jid)),
                    name="cleanup_expired_reservation",
                )
            except Exception as cleanup_exc:
                logger.error("Expired reservation cleanup failed for %s: %s", job_id, cleanup_exc)
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
                (lambda _, e=error: _set_status(job_id, "failed", error=str(e))),
                name="status_failed",
            )
        except Exception:
            logger.error("Failed to write failed status for %s", job_id)


def handle_failure(
    context: Any,
    job_id: str,
    user_id: str,
    error: Exception,
    *,
    ownership_verified: bool,
    reservation_mode: ReservationMode | None,
    reservation_done: bool,
) -> None:
    """Give the run slot back for a job that failed, then write it as failed."""
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
                        (lambda _, jid=job_id, uid=user_id: _expire_reservation_lease(jid, uid)),
                        name="expire_lease",
                    )
                except Exception:
                    logger.error("Failed to expire lease for %s", job_id)
    if ownership_verified:
        try:
            context.step(
                (lambda _, e=error: _set_status(job_id, "failed", error=str(e))),
                name="status_failed",
            )
        except Exception:
            logger.error("Failed to write failed status for %s", job_id)
