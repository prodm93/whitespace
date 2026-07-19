"""Thin gateway lambda: enqueue an orchestrate job and return its id.

Receives POST /api/orchestrate from API Gateway; checks tier limits (coarse
preflight), writes a pending row to the jobs table, sends the payload to the
SQS orchestrate queue, and returns {job_id, status: "pending"} immediately.
The durable_dispatcher then async-invokes the pipeline_orchestrator per the
established pattern.

Direct AWS_PROXY to the durable function is not viable: synchronous
invocation caps the execution at one <=15-min slice, and the ~29 s
gateway integration timeout would fire on long councils.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
JOBS_TABLE = os.environ.get("JOBS_TABLE", "")
ORCHESTRATE_QUEUE_URL = os.environ.get("ORCHESTRATE_QUEUE_URL", "")
USAGE_TABLE = os.environ.get("USAGE_TABLE", "")

_TIER_LIMITS: dict[str, int] = {
    "free": 2,
    "standard": 40,
    "pro": -1,
    "unlimited": -1,
}
_MONTHLY_RESET_TIERS = {"standard", "pro"}
_SECONDS_IN_30_DAYS = 30 * 24 * 3600


def handler(event: dict, context: object) -> dict:
    auth = ((event.get("requestContext") or {}).get("authorizer") or {}).get("lambda") or {}
    user_id: str = auth.get("user_id", "")
    tier: str = auth.get("tier", "free")

    if not user_id:
        return _response(401, {"error": "Unauthenticated"})

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Invalid JSON body"})

    intent = body.get("intent", "")
    if not intent:
        return _response(400, {"error": "intent is required"})

    deny = _preflight_check(user_id, tier)
    if deny:
        return deny

    job_id = uuid.uuid4().hex
    logger.info("Enqueuing orchestrate job_id=%s user=%s", job_id, user_id)

    import boto3

    dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
    dynamo.Table(JOBS_TABLE).put_item(
        Item={
            "job_id": job_id,
            "status": "pending",
            "user_id": user_id,
        }
    )

    message = {
        "job_id": job_id,
        "payload": {
            "intent": intent,
            "user_id": user_id,
            "selected_titles": body.get("selected_titles", []),
            "fresh_start": bool(body.get("fresh_start", False)),
            "profile_paths": body.get("profile_paths", []),
            "doc_paths": body.get("doc_paths", []),
            "domain": body.get("domain", ""),
            "keep_findings": bool(body.get("keep_findings", False)),
        },
    }

    sqs = boto3.client("sqs", region_name=AWS_REGION)
    sqs.send_message(QueueUrl=ORCHESTRATE_QUEUE_URL, MessageBody=json.dumps(message))

    return _response(200, {"job_id": job_id, "status": "pending"})


def _preflight_check(user_id: str, tier: str) -> dict | None:
    max_runs = _TIER_LIMITS.get(tier, 2)
    if max_runs == -1:
        return None
    if not USAGE_TABLE:
        return None

    import boto3

    table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(USAGE_TABLE)
    resp = table.get_item(Key={"user_id": user_id})
    item = resp.get("Item") or {}

    run_count = int(item.get("run_count", 0))
    last_reset = int(item.get("last_reset_ts", 0))

    if tier in _MONTHLY_RESET_TIERS:
        now = int(time.time())
        if now - last_reset > _SECONDS_IN_30_DAYS:
            run_count = 0
            table.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET run_count = :zero, last_reset_ts = :now",
                ExpressionAttributeValues={":zero": 0, ":now": now},
            )

    if run_count >= max_runs:
        return _response(429, {"error": f"Tier '{tier}' limit of {max_runs} runs reached"})
    return None


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
