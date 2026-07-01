"""Lambda handler — runs LangGraph pipelines (ingest, gap council, ideation council).

Triggered by SQS. Checkpoints state to DynamoDB via langgraph-checkpoint-aws
for human-in-the-loop interrupt/resume.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
CHECKPOINTS_TABLE = os.environ.get("CHECKPOINTS_TABLE", "")
CHECKPOINTS_BUCKET = os.environ.get("CHECKPOINTS_BUCKET", "")
JOBS_TABLE = os.environ.get("JOBS_TABLE", "")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", "")

_checkpointer = None


def _get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        from langgraph_checkpoint_aws import DynamoDBSaver

        kwargs = {
            "table_name": CHECKPOINTS_TABLE,
            "region_name": AWS_REGION,
            "ttl_seconds": 86400 * 7,
            "enable_checkpoint_compression": True,
        }
        if CHECKPOINTS_BUCKET:
            kwargs["s3_offload_config"] = {"bucket_name": CHECKPOINTS_BUCKET}
        _checkpointer = DynamoDBSaver(**kwargs)
    return _checkpointer


def handler(event: dict, context: object) -> dict:
    """SQS-triggered handler. Each record contains a job to execute."""
    for record in event.get("Records", []):
        body = json.loads(record["body"])
        job_id = body["job_id"]
        job_type = body["job_type"]
        payload = body.get("payload", {})

        logger.info("Processing job_id=%s type=%s", job_id, job_type)
        _update_job_status(job_id, "running")

        try:
            result = _run_pipeline(job_type, job_id, payload)
            _update_job_status(job_id, "completed", result=result)
        except Exception as exc:
            logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
            _update_job_status(job_id, "failed", error=str(exc))

    return {"statusCode": 200}


def _run_pipeline(job_type: str, job_id: str, payload: dict) -> dict:
    """Dispatch to the appropriate LangGraph pipeline."""
    checkpointer = _get_checkpointer()
    config = {"configurable": {"thread_id": job_id}}

    if job_type == "ingest":
        from whitespace.orchestration.ingest_graph import build_ingest_graph

        graph = build_ingest_graph(checkpointer=checkpointer)
        result = graph.invoke(payload, config)
    elif job_type == "gap_council":
        from whitespace.orchestration.gap_council_graph import build_gap_council_graph

        graph = build_gap_council_graph(checkpointer=checkpointer)
        result = graph.invoke(payload, config)
    elif job_type in ("ideation_council", "ideation_resume"):
        from whitespace.orchestration.ideation_council_graph import (
            build_ideation_council_graph,
        )

        graph = build_ideation_council_graph(checkpointer=checkpointer)
        result = graph.invoke(payload, config)
    else:
        raise ValueError(f"Unknown job_type: {job_type}")

    return result


def _update_job_status(
    job_id: str,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    import boto3

    dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = dynamo.Table(JOBS_TABLE)

    item: dict = {"job_id": job_id, "status": status}
    if result is not None:
        item["result"] = json.dumps(result)
    if error is not None:
        item["error"] = error

    table.put_item(Item=item)
