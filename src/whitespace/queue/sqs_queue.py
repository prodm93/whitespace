import asyncio
import json
import logging
import uuid

from whitespace.config import Config
from whitespace.domain import JobResult, JobStatus
from whitespace.queue.base import JobQueue

logger = logging.getLogger(__name__)


class SqsJobQueue(JobQueue):
    """Enqueues jobs to SQS and tracks status in DynamoDB. SaaS mode only."""

    def __init__(self, config: Config) -> None:
        import boto3

        self._sqs = boto3.client("sqs", region_name=config.aws_region)
        self._dynamo = boto3.resource("dynamodb", region_name=config.aws_region)
        self._queue_url = config.sqs_queue_url
        self._table = self._dynamo.Table(config.dynamodb_jobs_table)

    async def enqueue(self, job_type: str, payload: dict) -> str:
        job_id = uuid.uuid4().hex

        await asyncio.to_thread(
            self._table.put_item,
            Item={
                "job_id": job_id,
                "status": JobStatus.PENDING.value,
                "job_type": job_type,
                "result": None,
                "error": None,
            },
        )

        message_body = json.dumps(
            {
                "job_id": job_id,
                "job_type": job_type,
                "payload": payload,
            }
        )

        await asyncio.to_thread(
            self._sqs.send_message,
            QueueUrl=self._queue_url,
            MessageBody=message_body,
            MessageGroupId=job_type,
        )

        logger.info("SqsJobQueue: enqueued job_id=%s type=%s", job_id, job_type)
        return job_id

    async def get_status(self, job_id: str) -> JobResult:
        response = await asyncio.to_thread(self._table.get_item, Key={"job_id": job_id})
        item = response.get("Item")
        if item is None:
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                error=f"Unknown job_id={job_id}",
            )

        return JobResult(
            job_id=job_id,
            status=JobStatus(item["status"]),
            result=item.get("result"),
            error=item.get("error"),
        )
