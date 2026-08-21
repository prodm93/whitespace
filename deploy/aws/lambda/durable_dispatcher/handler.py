"""SQS-to-durable-function dispatcher.

Durable functions with execution timeouts beyond 15 minutes must be
invoked asynchronously, but SQS event-source mappings invoke
synchronously. This thin handler bridges the two: it drains SQS
records and async-invokes the durable pipeline function per job.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
PIPELINE_FUNCTION = os.environ.get("PIPELINE_FUNCTION", "")


def handler(event: dict, context: object) -> dict:
    import boto3

    client = boto3.client("lambda", region_name=AWS_REGION)
    for record in event.get("Records", []):
        body = json.loads(record["body"])
        job_id = body.get("job_id", "")
        if not job_id:
            raise ValueError(f"Record missing job_id: {record.get('messageId', '?')}")
        logger.info("Dispatching job_id=%s to durable pipeline", job_id)
        client.invoke(
            FunctionName=PIPELINE_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps(body),
            DurableExecutionName=job_id,
        )
    return {"statusCode": 200}
