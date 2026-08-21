"""Reservation state validation and lease transitions for the SaaS pipeline."""

from __future__ import annotations

import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
_JOBS_TABLE = os.environ.get("JOBS_TABLE", "")

_CLAIM_TTL_SECONDS = 25 * 3600

_USER_FACING_ERROR = "Unable to verify account usage. Please try again later."

ReservationMode = Literal["required", "not_required"]
ReservationStartOutcome = Literal["required", "not_required", "owned_expired"]
ActiveReservationStatus = Literal["pending", "claimed"]


class ReservationStateError(Exception):
    """Raised when the job row has missing or invalid reservation state."""


def _expire_reservation_lease(job_id: str, user_id: str) -> None:
    """Set reservation_expires_at to zero so the reclaim sweep picks it up."""
    import boto3
    from botocore.exceptions import ClientError

    try:
        boto3.resource("dynamodb", region_name=_AWS_REGION).Table(_JOBS_TABLE).update_item(
            Key={"job_id": job_id},
            ConditionExpression=(
                "attribute_exists(job_id) AND user_id = :uid "
                "AND reservation_status IN (:pending, :claimed)"
            ),
            UpdateExpression="SET reservation_expires_at = :zero",
            ExpressionAttributeValues={
                ":zero": 0,
                ":uid": user_id,
                ":pending": "pending",
                ":claimed": "claimed",
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning("Job %s not eligible for lease expiry", job_id)
            return
        raise


def _validate_and_start(job_id: str, user_id: str) -> ReservationStartOutcome:
    """Atomically verify ownership, start the job, and block rollback."""
    import time

    import boto3
    from botocore.exceptions import ClientError

    dynamo = boto3.resource("dynamodb", region_name=_AWS_REGION)
    now = int(time.time())

    try:
        dynamo.Table(_JOBS_TABLE).update_item(
            Key={"job_id": job_id},
            ConditionExpression=(
                "attribute_exists(job_id) AND user_id = :uid "
                "AND reservation_status = :pending AND reservation_expires_at > :now"
            ),
            UpdateExpression=(
                "SET #st = :running, reservation_status = :claimed, reservation_expires_at = :exp"
            ),
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":uid": user_id,
                ":pending": "pending",
                ":claimed": "claimed",
                ":running": "running",
                ":now": now,
                ":exp": now + _CLAIM_TTL_SECONDS,
            },
        )
        return "required"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise

    try:
        dynamo.Table(_JOBS_TABLE).update_item(
            Key={"job_id": job_id},
            ConditionExpression=(
                "attribute_exists(job_id) AND user_id = :uid AND reservation_status = :not_required"
            ),
            UpdateExpression="SET #st = :running",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":uid": user_id,
                ":not_required": "not_required",
                ":running": "running",
            },
        )
        return "not_required"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise

    resp = dynamo.Table(_JOBS_TABLE).get_item(Key={"job_id": job_id}, ConsistentRead=True)
    item = resp.get("Item")
    if not item:
        logger.error("Job row missing for %s", job_id)
        raise ReservationStateError(_USER_FACING_ERROR)
    if item.get("user_id") != user_id:
        logger.error(
            "Job %s belongs to %s, not %s",
            job_id,
            item.get("user_id"),
            user_id,
        )
        raise ReservationStateError(_USER_FACING_ERROR)
    status = item.get("reservation_status")
    unexpired = int(item.get("reservation_expires_at", 0)) > now
    if status == "claimed" and item.get("status") == "running" and unexpired:
        return "required"
    if status in ("pending", "claimed") and not unexpired:
        logger.error("Expired reservation_status '%s' for job %s", status, job_id)
        return "owned_expired"
    logger.error("Unexpected or expired reservation_status '%s' for job %s", status, job_id)
    raise ReservationStateError(_USER_FACING_ERROR)
