"""Atomic run-slot reservation for the enqueue gateway.

Reserve and job-create are one DynamoDB transaction so reclamation
cannot race the two writes. Two transaction paths handle migration
from legacy run_count-only rows to used_count rows.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from _txn import read_usage, reserve_txn

logger = logging.getLogger(__name__)

RESERVATION_TTL_SECONDS = 48 * 3600
_SAFE_CANCEL_CODES = {"None", "ConditionalCheckFailed"}

_ModernOutcome = Literal["ok", "denied", "legacy", "retry"]
_LegacyOutcome = Literal["ok", "denied", "race"]
ReserveOutcome = Literal["reserved", "cap_reached"]


def cancellation_reasons(exc: Any) -> list[dict[str, Any]]:
    """Extract reasons; raise if any are transient, capacity, or validation."""
    reasons = exc.response.get("CancellationReasons", [])
    for r in reasons:
        if r.get("Code", "None") not in _SAFE_CANCEL_CODES:
            raise exc
    return reasons


def reserve_slot(
    user_id: str,
    job_id: str,
    max_runs: int,
    usage_table: str,
    jobs_table: str,
    region: str,
) -> ReserveOutcome:
    """Atomically reserve a slot and create the job row.

    Tries the modern path first (row has used_count); falls back to
    legacy initialization (row has only run_count or is new).
    """
    import boto3

    client = boto3.client("dynamodb", region_name=region)

    result = _try_modern(client, user_id, job_id, max_runs, usage_table, jobs_table, region, "m1")
    if result == "ok":
        return "reserved"
    if result == "denied":
        return "cap_reached"
    if result == "retry":
        result = _try_modern(
            client, user_id, job_id, max_runs, usage_table, jobs_table, region, "m2"
        )
        if result == "ok":
            return "reserved"
        if result == "denied":
            return "cap_reached"

    result = _try_legacy(client, user_id, job_id, max_runs, usage_table, jobs_table, region, "l1")
    if result == "ok":
        return "reserved"
    if result == "denied":
        return "cap_reached"

    result = _try_modern(client, user_id, job_id, max_runs, usage_table, jobs_table, region, "m3")
    if result == "ok":
        return "reserved"
    if result == "denied":
        return "cap_reached"
    raise RuntimeError("Unable to verify account usage. Please try again later.")


def _try_modern(
    client: Any,
    user_id: str,
    job_id: str,
    max_runs: int,
    usage_table: str,
    jobs_table: str,
    region: str,
    token_suffix: str,
) -> _ModernOutcome:
    """Reserve assuming used_count exists.

    Returns 'ok', 'denied', 'legacy', or 'retry'.
    """
    from botocore.exceptions import ClientError

    now = str(int(time.time()))
    expires = str(int(time.time()) + RESERVATION_TTL_SECONDS)
    try:
        reserve_txn(
            client,
            usage_table,
            jobs_table,
            user_id,
            job_id,
            expires,
            condition="attribute_exists(used_count) AND used_count < :cap",
            update=(
                "SET used_count = used_count + :one, "
                "pending_count = if_not_exists(pending_count, :zero) + :one, "
                "run_count = if_not_exists(run_count, :zero), "
                "version = if_not_exists(version, :zero) + :one, "
                "last_reset_ts = if_not_exists(last_reset_ts, :now) "
                "ADD pending_job_ids :jid"
            ),
            values={
                ":zero": {"N": "0"},
                ":one": {"N": "1"},
                ":cap": {"N": str(max_runs)},
                ":now": {"N": now},
                ":jid": {"SS": [job_id]},
            },
            token_suffix=token_suffix,
        )
        return "ok"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        reasons = cancellation_reasons(exc)
        if reasons[0].get("Code") != "ConditionalCheckFailed":
            raise
        item = read_usage(region, usage_table, user_id)
        if not item or "used_count" not in item:
            return "legacy"
        if int(item.get("used_count", 0)) < max_runs:
            return "retry"
        return "denied"


def _try_legacy(
    client: Any,
    user_id: str,
    job_id: str,
    max_runs: int,
    usage_table: str,
    jobs_table: str,
    region: str,
    token_suffix: str,
) -> _LegacyOutcome:
    """Initialize used_count from legacy run_count-only rows.

    Returns 'ok', 'denied', or 'race' (another request created used_count).
    """
    from botocore.exceptions import ClientError

    now = str(int(time.time()))
    expires = str(int(time.time()) + RESERVATION_TTL_SECONDS)
    try:
        reserve_txn(
            client,
            usage_table,
            jobs_table,
            user_id,
            job_id,
            expires,
            condition=(
                "attribute_not_exists(used_count) AND "
                "(attribute_not_exists(run_count) OR run_count < :cap)"
            ),
            update=(
                "SET used_count = if_not_exists(run_count, :zero) + :one, "
                "pending_count = if_not_exists(pending_count, :zero) + :one, "
                "run_count = if_not_exists(run_count, :zero), "
                "version = if_not_exists(version, :zero) + :one, "
                "last_reset_ts = if_not_exists(last_reset_ts, :now) "
                "ADD pending_job_ids :jid"
            ),
            values={
                ":zero": {"N": "0"},
                ":one": {"N": "1"},
                ":cap": {"N": str(max_runs)},
                ":now": {"N": now},
                ":jid": {"SS": [job_id]},
            },
            token_suffix=token_suffix,
        )
        return "ok"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        reasons = cancellation_reasons(exc)
        if reasons[0].get("Code") != "ConditionalCheckFailed":
            raise
        item = read_usage(region, usage_table, user_id)
        return "race" if (item and "used_count" in item) else "denied"
