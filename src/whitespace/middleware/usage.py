import asyncio
import logging
import time

from fastapi import Depends, HTTPException, Request

from whitespace.config import Config
from whitespace.middleware.auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

TIER_LIMITS: dict[str, dict[str, int]] = {
    "free": {"runs": 2, "files": 3, "upload_mb": 50},
    "standard": {"runs": 40, "files": 10, "upload_mb": 200},
    "pro": {"runs": -1, "files": 50, "upload_mb": 1024},
    "unlimited": {"runs": -1, "files": -1, "upload_mb": -1},
}

MONTHLY_RESET_TIERS = {"standard", "pro"}


async def check_usage(
    request: Request,
    user: CurrentUser = Depends(get_current_user),  # noqa: B008
) -> None:
    """Enforce tier-based usage limits.

    In BYOK mode this is a no-op. In SaaS mode, reads run counts
    from DynamoDB and returns 429 when the tier limit is exceeded.
    """
    config: Config = request.app.state.config
    if config.mode == "byok":
        return

    await _enforce_run_limit(config, user)


async def _enforce_run_limit(config: Config, user: CurrentUser) -> None:
    import boto3

    limits = TIER_LIMITS.get(user.tier)
    if limits is None:
        raise HTTPException(status_code=403, detail=f"Unknown tier: {user.tier}")

    max_runs = limits["runs"]
    if max_runs == -1:
        return

    dynamo = boto3.resource("dynamodb", region_name=config.aws_region)
    table = dynamo.Table(config.dynamodb_usage_table)

    response = await asyncio.to_thread(table.get_item, Key={"user_id": user.user_id})
    item = response.get("Item")

    current_count = 0
    if item is not None:
        current_count = item.get("run_count", 0)
        last_reset = item.get("last_reset_ts", 0)

        if user.tier in MONTHLY_RESET_TIERS:
            now = time.time()
            seconds_in_30_days = 30 * 24 * 3600
            if now - last_reset > seconds_in_30_days:
                current_count = 0
                await asyncio.to_thread(
                    table.update_item,
                    Key={"user_id": user.user_id},
                    UpdateExpression="SET run_count = :zero, last_reset_ts = :now",
                    ExpressionAttributeValues={":zero": 0, ":now": int(now)},
                )

    if current_count >= max_runs:
        raise HTTPException(
            status_code=429,
            detail=f"Tier '{user.tier}' limit of {max_runs} runs reached",
        )


async def increment_run_count(config: Config, user_id: str) -> None:
    """Increment the run counter after a successful job enqueue."""
    import time as _time

    import boto3

    dynamo = boto3.resource("dynamodb", region_name=config.aws_region)
    table = dynamo.Table(config.dynamodb_usage_table)

    await asyncio.to_thread(
        table.update_item,
        Key={"user_id": user_id},
        UpdateExpression=(
            "SET run_count = if_not_exists(run_count, :zero) + :one, "
            "last_reset_ts = if_not_exists(last_reset_ts, :now)"
        ),
        ExpressionAttributeValues={
            ":zero": 0,
            ":one": 1,
            ":now": int(_time.time()),
        },
    )
