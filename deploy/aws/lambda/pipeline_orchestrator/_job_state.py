"""DynamoDB and S3 job-state writes for the SaaS durable orchestrator."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
_JOBS_TABLE = os.environ.get("JOBS_TABLE", "")
_RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", "")
_USAGE_TABLE = os.environ.get("USAGE_TABLE", "")


def _set_status(
    job_id: str,
    status: str,
    result_key: str | None = None,
    error: str | None = None,
) -> None:
    import boto3

    names: dict[str, str] = {"#st": "status"}
    vals: dict[str, Any] = {":st": status}
    expr = "SET #st = :st"
    if result_key:
        expr += ", result_key = :rk"
        vals[":rk"] = result_key
    if error:
        expr += ", #err = :err"
        names["#err"] = "error"
        vals[":err"] = error
    boto3.resource("dynamodb", region_name=_AWS_REGION).Table(_JOBS_TABLE).update_item(
        Key={"job_id": job_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=vals,
    )


def _increment_run_count(user_id: str) -> None:
    import time

    import boto3

    if not user_id or not _USAGE_TABLE:
        return
    now = int(time.time())
    boto3.resource("dynamodb", region_name=_AWS_REGION).Table(_USAGE_TABLE).update_item(
        Key={"user_id": user_id},
        UpdateExpression=(
            "SET run_count = if_not_exists(run_count, :zero) + :one, "
            "last_reset_ts = if_not_exists(last_reset_ts, :now)"
        ),
        ExpressionAttributeValues={":zero": 0, ":one": 1, ":now": now},
    )


def _publish(job_id: str, result: dict[str, Any]) -> None:
    import boto3

    key = f"results/{job_id}.json"
    boto3.client("s3", region_name=_AWS_REGION).put_object(
        Bucket=_RESULTS_BUCKET, Key=key, Body=json.dumps(result)
    )
    _set_status(job_id, "completed", result_key=key)
