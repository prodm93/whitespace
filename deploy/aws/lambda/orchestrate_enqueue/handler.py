"""Thin gateway lambda: enqueue an orchestrate job and return its id.

Receives POST /api/orchestrate from API Gateway; reserves a run slot
(atomic conditional update on the usage table), writes a pending row to
the jobs table, sends the payload to the SQS orchestrate queue, and
returns {job_id, status: "pending"} immediately. The durable_dispatcher
then async-invokes the pipeline_orchestrator per the established pattern.

Direct AWS_PROXY to the durable function is not viable: synchronous
invocation caps the execution at one <=15-min slice, and the ~29 s
gateway integration timeout would fire on long councils.
"""

from __future__ import annotations

import json
import logging
import os
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

    job_id = uuid.uuid4().hex

    deny = _preflight_and_reserve(user_id, tier, job_id)
    if deny:
        return deny

    logger.info("Enqueuing orchestrate job_id=%s user=%s", job_id, user_id)

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    try:
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
    except (ClientError, BotoCoreError):
        _cleanup_on_sqs_failure(user_id, tier, job_id)
        raise

    return _response(200, {"job_id": job_id, "status": "pending"})


def _preflight_and_reserve(user_id: str, tier: str, job_id: str) -> dict | None:
    if tier not in _TIER_LIMITS:
        return _response(403, {"error": f"Unknown tier: {tier}"})
    if not USAGE_TABLE:
        return _response(
            500,
            {"error": "Unable to verify account usage. Please try again later."},
        )

    max_runs = _TIER_LIMITS[tier]

    if max_runs == -1:
        _create_unlimited_job(user_id, job_id)
        return None

    from _reclaim import reclaim_expired
    from _reservation import reserve_slot
    from _reset import ResetExhaustedError, maybe_monthly_reset

    reclaim_expired(user_id, USAGE_TABLE, JOBS_TABLE, AWS_REGION)

    try:
        maybe_monthly_reset(user_id, tier, USAGE_TABLE, AWS_REGION)
    except ResetExhaustedError as rse:
        return _response(500, {"error": str(rse)})

    try:
        outcome = reserve_slot(user_id, job_id, max_runs, USAGE_TABLE, JOBS_TABLE, AWS_REGION)
    except RuntimeError:
        return _response(
            500,
            {"error": "Unable to verify account usage. Please try again later."},
        )
    if outcome == "cap_reached":
        return _response(429, {"error": f"Tier '{tier}' limit of {max_runs} runs reached"})
    return None


def _create_unlimited_job(user_id: str, job_id: str) -> None:
    import boto3

    dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
    dynamo.Table(JOBS_TABLE).put_item(
        Item={
            "job_id": job_id,
            "status": "pending",
            "user_id": user_id,
            "reservation_status": "not_required",
        }
    )


def _cleanup_on_sqs_failure(user_id: str, tier: str, job_id: str) -> None:
    from botocore.exceptions import BotoCoreError, ClientError

    max_runs = _TIER_LIMITS.get(tier, 0)
    try:
        if max_runs == -1:
            import boto3

            dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
            dynamo.Table(JOBS_TABLE).delete_item(Key={"job_id": job_id})
        else:
            from _reclaim import rollback_reservation

            rollback_reservation(user_id, job_id, USAGE_TABLE, JOBS_TABLE, AWS_REGION)
    except (ClientError, BotoCoreError):
        logger.error("Cleanup failed for job %s; reclamation will handle it", job_id)


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
