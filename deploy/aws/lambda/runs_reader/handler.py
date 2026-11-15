"""Read routes for SaaS job status and run rehydration.

Kept separate from orchestrate_enqueue so the write path stays a
stdlib-only zip with write-only IAM; this function alone carries
whitespace and pydantic behind a read-only DynamoDB and S3 role.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

JOBS_TABLE = os.environ.get("JOBS_TABLE", "")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", "")


_JOB_ROUTE = "GET /api/jobs/{jobId}"
_LATEST_ROUTE = "GET /api/runs/latest"


def handler(event: dict, context: object) -> dict:
    route_key: str = event.get("routeKey", "")
    if route_key not in (_JOB_ROUTE, _LATEST_ROUTE):
        return _response(404, {"error": f"Unknown route: {route_key}"})
    caller = _caller_id(event)
    if not caller:
        return _response(401, {"error": "Unauthenticated"})
    if route_key == _JOB_ROUTE:
        return _get_job(event, caller)
    return _get_runs_latest(caller)


def _caller_id(event: dict) -> str:
    """Return the user ID that the authoriser set, or ``""`` when it is not a string."""
    auth = ((event.get("requestContext") or {}).get("authorizer") or {}).get("lambda") or {}
    user_id = auth.get("user_id")
    return user_id if isinstance(user_id, str) else ""


def _get_job(event: dict, caller: str) -> dict:
    """Return the status and result of a job of ``caller``.

    A job of a different user, a job with no owner and an unknown job get the same 404, so
    a caller cannot tell which job IDs exist. The result is read only for the owner.
    """
    path_params: dict = event.get("pathParameters") or {}
    job_id: str = path_params.get("jobId", "")
    if not job_id:
        return _response(400, {"error": "jobId is required"})

    import boto3

    region = os.environ.get("AWS_REGION", "")
    dynamo = boto3.resource("dynamodb", region_name=region)
    resp = dynamo.Table(JOBS_TABLE).get_item(Key={"job_id": job_id})
    item: dict | None = resp.get("Item")

    if item is None or item.get("user_id") != caller:
        if item is not None:
            logger.warning("Job %s was asked for by %s, who does not own it", job_id, caller)
        return _response(404, {"error": "Job not found"})

    result: Any = None
    if "result_key" in item:
        s3 = boto3.client("s3", region_name=region)
        obj = s3.get_object(Bucket=RESULTS_BUCKET, Key=item["result_key"])
        result = json.loads(obj["Body"].read())

    return _response(
        200,
        {
            "job_id": job_id,
            "status": item.get("status", "unknown"),
            "result": result,
            "error": item.get("error"),
        },
    )


def _get_runs_latest(caller: str) -> dict:
    """Return the latest gap run of ``caller`` and its ideation runs."""
    from whitespace.store.dynamo_store import DynamoSessionStore

    region = os.environ.get("AWS_REGION", "")
    store = DynamoSessionStore(SESSIONS_TABLE, region, owner=caller)

    gap_run = asyncio.run(store.get_latest_gap_run())
    if gap_run is None:
        return _response(200, {"gap_run": None, "idea_runs": []})

    idea_runs = asyncio.run(store.list_idea_runs(gap_run.run_id))
    return _response(
        200,
        {
            "gap_run": gap_run.model_dump(mode="json"),
            "idea_runs": [r.model_dump(mode="json") for r in idea_runs],
        },
    )


def _response(status: int, body: Any) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
