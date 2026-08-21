"""DynamoDB job-state reads and writes for the SaaS durable orchestrator."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
_JOBS_TABLE = os.environ.get("JOBS_TABLE", "")
_RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", "")


def _set_status(
    job_id: str,
    status: str,
    result_key: str | None = None,
    error: str | None = None,
) -> None:
    import boto3
    from botocore.exceptions import ClientError

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
    try:
        boto3.resource("dynamodb", region_name=_AWS_REGION).Table(_JOBS_TABLE).update_item(
            Key={"job_id": job_id},
            ConditionExpression="attribute_exists(job_id)",
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=vals,
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning("Job row %s absent; skipping status write", job_id)
            return
        raise


def _publish(job_id: str, result: dict[str, Any]) -> None:
    import boto3

    key = f"results/{job_id}.json"
    boto3.client("s3", region_name=_AWS_REGION).put_object(
        Bucket=_RESULTS_BUCKET, Key=key, Body=json.dumps(result)
    )
    _set_status(job_id, "completed", result_key=key)
