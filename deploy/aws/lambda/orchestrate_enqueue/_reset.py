"""Monthly usage counter reset with bounded CAS retry.

Resets run_count to zero while preserving pending reservations
(used_count = pending_count). Uses a version counter for
compare-and-swap; fails closed after repeated conflicts.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_MONTHLY_RESET_TIERS = {"standard", "pro"}
_SECONDS_IN_30_DAYS = 30 * 24 * 3600
_MAX_CAS_ATTEMPTS = 3


class ResetExhaustedError(Exception):
    """Raised when monthly reset CAS retry is exhausted."""


def maybe_monthly_reset(
    user_id: str,
    tier: str,
    usage_table: str,
    region: str,
) -> None:
    """Reset monthly counters if the period has elapsed.

    Raises ResetExhaustedError on CAS exhaustion (fail closed).
    """
    if tier not in _MONTHLY_RESET_TIERS:
        return

    import boto3
    from botocore.exceptions import ClientError

    table = boto3.resource("dynamodb", region_name=region).Table(usage_table)

    for attempt in range(_MAX_CAS_ATTEMPTS):
        resp = table.get_item(Key={"user_id": user_id}, ConsistentRead=True)
        item = resp.get("Item") or {}
        last_reset = int(item.get("last_reset_ts", 0))
        now = int(time.time())
        if now - last_reset <= _SECONDS_IN_30_DAYS:
            return

        read_version = int(item.get("version", 0))
        try:
            table.update_item(
                Key={"user_id": user_id},
                ConditionExpression="attribute_not_exists(version) OR version = :rv",
                UpdateExpression=(
                    "SET run_count = :zero, "
                    "used_count = if_not_exists(pending_count, :zero), "
                    "last_reset_ts = :now, "
                    "version = if_not_exists(version, :zero) + :one"
                ),
                ExpressionAttributeValues={
                    ":zero": 0,
                    ":one": 1,
                    ":now": now,
                    ":rv": read_version,
                },
            )
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            logger.info(
                "Monthly reset CAS conflict for user %s (attempt %d/%d)",
                user_id,
                attempt + 1,
                _MAX_CAS_ATTEMPTS,
            )

    logger.error(
        "Monthly reset CAS exhausted for user %s after %d attempts",
        user_id,
        _MAX_CAS_ATTEMPTS,
    )
    raise ResetExhaustedError("Unable to verify account usage. Please try again later.")
