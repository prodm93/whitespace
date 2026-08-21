"""Cross-table reservation transactions for the durable pipeline.

Convert (claimed to charged), release (pending/claimed to released),
and state-aware cleanup. All multi-row mutations use TransactWriteItems
with idempotency guards verified by consistent reads.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from _reservation_state import ActiveReservationStatus, ReservationStateError

_MISSING_TABLE_MSG = "Unable to verify account usage. Please try again later."


def _validate_usage_config() -> None:
    """Fail closed if the usage table is not configured."""
    if not _USAGE_TABLE:
        raise ReservationStateError(_MISSING_TABLE_MSG)


logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
_JOBS_TABLE = os.environ.get("JOBS_TABLE", "")
_USAGE_TABLE = os.environ.get("USAGE_TABLE", "")

_SAFE_CANCEL_CODES = {"None", "ConditionalCheckFailed"}


def _cancellation_reasons(exc: Any) -> list[dict[str, Any]]:
    """Extract reasons; raise if any are transient, capacity, or validation."""
    reasons = exc.response.get("CancellationReasons", [])
    for r in reasons:
        if r.get("Code", "None") not in _SAFE_CANCEL_CODES:
            raise exc
    return reasons


def _read_job(job_id: str) -> dict[str, Any] | None:
    import boto3

    return (
        boto3.resource("dynamodb", region_name=_AWS_REGION)
        .Table(_JOBS_TABLE)
        .get_item(Key={"job_id": job_id}, ConsistentRead=True)
        .get("Item")
    )


def _convert_reservation(user_id: str, job_id: str) -> None:
    """Atomically convert a claimed reservation to a permanent charge."""
    import boto3
    from botocore.exceptions import ClientError

    if not user_id:
        return
    if not _USAGE_TABLE:
        raise ReservationStateError(_MISSING_TABLE_MSG)
    client = boto3.client("dynamodb", region_name=_AWS_REGION)
    try:
        client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": _JOBS_TABLE,
                        "Key": {"job_id": {"S": job_id}},
                        "ConditionExpression": "reservation_status = :claimed",
                        "UpdateExpression": "SET reservation_status = :charged",
                        "ExpressionAttributeValues": {
                            ":claimed": {"S": "claimed"},
                            ":charged": {"S": "charged"},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": _USAGE_TABLE,
                        "Key": {"user_id": {"S": user_id}},
                        "ConditionExpression": "contains(pending_job_ids, :jstr)",
                        "UpdateExpression": (
                            "SET run_count = if_not_exists(run_count, :zero) + :one, "
                            "pending_count = pending_count - :one, "
                            "version = version + :one "
                            "DELETE pending_job_ids :jid"
                        ),
                        "ExpressionAttributeValues": {
                            ":zero": {"N": "0"},
                            ":one": {"N": "1"},
                            ":jid": {"SS": [job_id]},
                            ":jstr": {"S": job_id},
                        },
                    }
                },
            ]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        reasons = _cancellation_reasons(exc)
        job_code = reasons[0].get("Code", "None") if reasons else "None"
        usage_code = reasons[1].get("Code", "None") if len(reasons) > 1 else "None"
        if job_code == "ConditionalCheckFailed":
            job = _read_job(job_id)
            if job and job.get("reservation_status") == "charged":
                logger.info("Convert already resolved for job %s", job_id)
                return
        if usage_code == "ConditionalCheckFailed":
            logger.error("Usage invariant violation on convert for job %s", job_id)
        raise


def _release_reservation(user_id: str, job_id: str, from_status: ActiveReservationStatus) -> None:
    """Atomically release a reservation (from pending or claimed)."""
    import boto3
    from botocore.exceptions import ClientError

    if not user_id:
        return
    if not _USAGE_TABLE:
        raise ReservationStateError(_MISSING_TABLE_MSG)
    client = boto3.client("dynamodb", region_name=_AWS_REGION)
    try:
        client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": _JOBS_TABLE,
                        "Key": {"job_id": {"S": job_id}},
                        "ConditionExpression": "reservation_status = :st",
                        "UpdateExpression": "SET reservation_status = :released",
                        "ExpressionAttributeValues": {
                            ":st": {"S": from_status},
                            ":released": {"S": "released"},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": _USAGE_TABLE,
                        "Key": {"user_id": {"S": user_id}},
                        "ConditionExpression": "contains(pending_job_ids, :jstr)",
                        "UpdateExpression": (
                            "SET used_count = used_count - :one, "
                            "pending_count = pending_count - :one, "
                            "version = version + :one "
                            "DELETE pending_job_ids :jid"
                        ),
                        "ExpressionAttributeValues": {
                            ":one": {"N": "1"},
                            ":jid": {"SS": [job_id]},
                            ":jstr": {"S": job_id},
                        },
                    }
                },
            ]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        reasons = _cancellation_reasons(exc)
        job_code = reasons[0].get("Code", "None") if reasons else "None"
        usage_code = reasons[1].get("Code", "None") if len(reasons) > 1 else "None"
        if job_code == "ConditionalCheckFailed":
            job = _read_job(job_id)
            if job and job.get("reservation_status") == "released":
                logger.info("Release already resolved for job %s", job_id)
                return
        if usage_code == "ConditionalCheckFailed":
            logger.error("Usage invariant violation on release for job %s", job_id)
        raise


def _cleanup_reservation(user_id: str, job_id: str) -> None:
    """State-aware cleanup: read actual state, release if still active.

    Non-idempotent failures propagate to the caller for logging.
    """
    job = _read_job(job_id)
    if not job:
        return
    status = job.get("reservation_status")
    if status in ("charged", "released", "not_required"):
        return
    if status == "claimed":
        _release_reservation(user_id, job_id, "claimed")
    elif status == "pending":
        _release_reservation(user_id, job_id, "pending")
