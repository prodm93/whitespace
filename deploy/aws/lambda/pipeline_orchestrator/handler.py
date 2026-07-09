"""SaaS analysis pipeline as a Lambda durable function.

One durable execution covers the whole flow: profile extraction, the
research-first gap analysis, a zero-compute-cost callback wait while
the human selects gaps, then ideation. Every stage is a checkpointed
step; a crash, timeout or redeploy replays past completed steps
instead of redoing them.

Invocation: SQS → dispatcher (async invoke) → this function. Direct
SQS event-source mapping is deliberately avoided: it invokes
synchronously, which caps the execution at one 15-minute slice.

Follow-up (tracked): chunk the graph build per document so the
gap_analysis step stays well inside a single invocation slice on
large corpora.
"""

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING

from aws_durable_execution_sdk import DurableContext, durable_execution

if TYPE_CHECKING:
    from whitespace.config import Config
    from whitespace.store.base import SessionStore

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
JOBS_TABLE = os.environ.get("JOBS_TABLE", "")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", "")

_pipeline = None


def _get_pipeline():
    """Cold-start singleton; reused across invocation slices."""
    global _pipeline
    if _pipeline is None:
        from whitespace.config import Config
        from whitespace.orchestration.pipeline import Pipeline

        config = Config()
        session_store = _build_session_store(config)
        _pipeline = Pipeline.from_config(config, session_store=session_store)
        asyncio.run(_pipeline.initialise())
    return _pipeline


def _build_session_store(config: "Config") -> "SessionStore":
    if config.sessions_table:
        from whitespace.store.dynamo_store import DynamoSessionStore

        return DynamoSessionStore(config.sessions_table, config.aws_region)

    logger.warning("SESSIONS_TABLE not set; SaaS session persistence is disabled")
    from whitespace.store.noop_store import NoopSessionStore

    return NoopSessionStore()


@durable_execution
def handler(event: dict, context: DurableContext) -> dict:
    job_id = event["job_id"]
    payload = event.get("payload", {})

    context.step(lambda: _set_status(job_id, "running"), name="status_running")
    profile = context.step(lambda: _extract_profile(payload), name="extract_profile")
    needs = context.step(lambda: _gap_analysis(job_id, payload, profile), name="gap_analysis")
    context.step(
        lambda: _publish(job_id, "awaiting_selection", {"needs": needs}),
        name="publish_gaps",
    )

    # Zero-cost suspension: the execution sleeps until POST /api/ideate
    # sends the callback with the user's selections.
    selection_raw = context.wait_for_callback(
        lambda token: _store_callback_token(job_id, token),
        name="await_gap_selection",
    )
    selected_titles = json.loads(selection_raw or "{}").get("selected_titles", [])

    proposals = context.step(lambda: _ideation(profile, needs, selected_titles), name="ideation")
    context.step(
        lambda: _publish(job_id, "completed", {"needs": needs, "proposals": proposals}),
        name="publish_results",
    )
    return {"job_id": job_id, "status": "completed"}


def _extract_profile(payload: dict) -> dict:
    pipeline = _get_pipeline()
    paths = payload.get("profile_paths", [])
    if not paths:
        raise RuntimeError("No profile documents supplied")
    profile = asyncio.run(pipeline.extract_profile(paths))
    return profile.model_dump()


def _gap_analysis(job_id: str, payload: dict, profile: dict) -> list[dict]:
    from whitespace.schemas.profile import ProfessionalProfile

    pipeline = _get_pipeline()
    needs = asyncio.run(
        pipeline.analyse_gaps(
            ProfessionalProfile.model_validate(profile),
            ", ".join(payload.get("domain_keywords", [])),
            payload.get("profile_paths", []) + payload.get("domain_paths", []),
            keep_findings=bool(payload.get("keep_findings", False)),
            run_id=job_id,
        )
    )
    return [n.model_dump() for n in needs]


def _ideation(profile: dict, needs: list[dict], selected_titles: list[str]) -> list[dict]:
    from whitespace.schemas.gap import UnmetNeed
    from whitespace.schemas.profile import ProfessionalProfile

    pipeline = _get_pipeline()
    chosen = [UnmetNeed.model_validate(n) for n in needs if n.get("title") in selected_titles]
    proposals = asyncio.run(pipeline.ideate(chosen, ProfessionalProfile.model_validate(profile)))
    return [p.model_dump() for p in proposals]


def _store_callback_token(job_id: str, token: str) -> None:
    """Persist the callback token so the ideate route can resume us."""
    import boto3

    dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
    dynamo.Table(JOBS_TABLE).update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET callback_token = :t",
        ExpressionAttributeValues={":t": token},
    )


def _publish(job_id: str, status: str, result: dict) -> None:
    import boto3

    s3 = boto3.client("s3", region_name=AWS_REGION)
    key = f"results/{job_id}.json"
    s3.put_object(Bucket=RESULTS_BUCKET, Key=key, Body=json.dumps(result))
    _set_status(job_id, status, result_key=key)


def _set_status(job_id: str, status: str, result_key: str | None = None) -> None:
    import boto3

    dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
    item: dict = {"job_id": job_id, "status": status}
    if result_key:
        item["result_key"] = result_key
    dynamo.Table(JOBS_TABLE).put_item(Item=item)
