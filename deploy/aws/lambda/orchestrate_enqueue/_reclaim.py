"""Reservation cleanup: immediate rollback and expired-slot reclamation.

rollback_reservation undoes a reservation after SQS send failure.
reclaim_expired scans a user's pending_job_ids set, checks each job
row for expiry, and atomically releases expired reservations.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from _reservation import cancellation_reasons
from _txn import counter_release_item, release_counter, release_via_transaction

logger = logging.getLogger(__name__)


def rollback_reservation(
    user_id: str,
    job_id: str,
    usage_table: str,
    jobs_table: str,
    region: str,
) -> None:
    """Undo a reservation after SQS failure.

    Callers handle errors; reclamation covers remaining cases.
    """
    import boto3

    client = boto3.client("dynamodb", region_name=region)
    client.transact_write_items(
        TransactItems=[
            {
                "Delete": {
                    "TableName": jobs_table,
                    "Key": {"job_id": {"S": job_id}},
                    "ConditionExpression": "reservation_status = :pending",
                    "ExpressionAttributeValues": {":pending": {"S": "pending"}},
                }
            },
            counter_release_item(user_id, job_id, usage_table),
        ]
    )


def reclaim_expired(
    user_id: str,
    usage_table: str,
    jobs_table: str,
    region: str,
) -> int:
    """Release expired pending/claimed reservations for a user."""
    import boto3
    from botocore.exceptions import ClientError

    dynamo = boto3.resource("dynamodb", region_name=region)
    usage = dynamo.Table(usage_table)
    resp = usage.get_item(
        Key={"user_id": user_id},
        ConsistentRead=True,
    )
    item = resp.get("Item") or {}
    pending_ids = item.get("pending_job_ids") or set()
    if not pending_ids:
        return 0

    jobs = dynamo.Table(jobs_table)
    client = boto3.client("dynamodb", region_name=region)
    now = int(time.time())
    reclaimed = 0

    for jid in list(pending_ids):
        job_item = jobs.get_item(
            Key={"job_id": jid},
            ConsistentRead=True,
        ).get("Item")
        if job_item is None:
            release_counter(user_id, jid, usage_table, dynamo)
            reclaimed += 1
            continue
        status = job_item.get("reservation_status")
        if status not in ("pending", "claimed"):
            logger.error(
                "Invariant violation: job %s has status '%s' but remains in pending_job_ids",
                jid,
                status,
            )
            raise RuntimeError(
                f"Invariant violation: job {jid} status '{status}' in pending_job_ids"
            )
        if int(job_item.get("reservation_expires_at", 0)) >= now:
            continue
        try:
            release_via_transaction(
                client,
                user_id,
                jid,
                status,
                usage_table,
                jobs_table,
            )
            reclaimed += 1
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            reasons = cancellation_reasons(exc)
            _handle_reclaim_ccf(reasons, jid, jobs, user_id, usage)

    return reclaimed


def _handle_reclaim_ccf(
    reasons: list[dict[str, Any]],
    job_id: str,
    jobs_table: object,
    user_id: str,
    usage_table: object,
) -> None:
    """Classify ConditionalCheckFailed after a reclaim release attempt."""
    job_code = reasons[0].get("Code", "None") if reasons else "None"
    usage_code = reasons[1].get("Code", "None") if len(reasons) > 1 else "None"

    if job_code == "ConditionalCheckFailed":
        job_now = jobs_table.get_item(  # type: ignore[union-attr]
            Key={"job_id": job_id},
            ConsistentRead=True,
        ).get("Item")
        usage_now = usage_table.get_item(  # type: ignore[union-attr]
            Key={"user_id": user_id},
            ConsistentRead=True,
        ).get("Item")
        pending = (usage_now or {}).get("pending_job_ids") or set()
        terminal = job_now and job_now.get("reservation_status") in (
            "charged",
            "released",
            "not_required",
        )
        if terminal and job_id not in pending:
            logger.info(
                "Reclaim idempotent for job %s (now %s)",
                job_id,
                job_now.get("reservation_status"),
            )
            return
        raise RuntimeError(
            f"Reclaim failed for job {job_id}: "
            f"status={job_now.get('reservation_status') if job_now else 'missing'}, "
            f"in_pending={job_id in pending}"
        )

    if usage_code == "ConditionalCheckFailed":
        logger.error(
            "Usage invariant violation reclaiming job %s for user %s",
            job_id,
            user_id,
        )
        raise RuntimeError(f"Usage invariant violation: job {job_id} not in pending_job_ids")
