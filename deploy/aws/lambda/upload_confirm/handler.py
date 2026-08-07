"""Handles upload reservation lifecycle events.

Responds to two S3 event types:
- ObjectCreated:Post: confirms a presigned upload completed by
  transitioning the reservation from pending to confirmed.
- LifecycleExpiration:Delete: decrements the active file counter
  when S3 lifecycle rules remove expired objects.

Reservations are leases. If no reservation exists when an upload
event arrives, the object is deleted from S3.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import unquote_plus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
RESERVATIONS_TABLE = os.environ.get("RESERVATIONS_TABLE", "")
USAGE_TABLE = os.environ.get("USAGE_TABLE", "")
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")


def handler(event: dict, context: object) -> None:
    import boto3

    dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)
    s3 = boto3.client("s3", region_name=AWS_REGION)

    for record in event.get("Records", []):
        s3_key = unquote_plus(record["s3"]["object"]["key"])
        event_name = record.get("eventName", "")
        user_id = _extract_user_id(s3_key)
        if not user_id:
            logger.warning("Cannot extract user_id from s3_key=%s", s3_key)
            continue

        if event_name.startswith("ObjectCreated"):
            _handle_created(dynamodb, s3, s3_key)
        elif "LifecycleExpiration" in event_name:
            _handle_lifecycle_delete(dynamodb, s3_key, user_id)
        else:
            logger.info("Ignoring event %s for s3_key=%s", event_name, s3_key)


def _extract_user_id(s3_key: str) -> str | None:
    parts = s3_key.split("/")
    return parts[1] if len(parts) >= 3 and parts[0] == "uploads" else None


def _handle_created(dynamodb, s3, s3_key: str) -> None:
    try:
        dynamodb.update_item(
            TableName=RESERVATIONS_TABLE,
            Key={"s3_key": {"S": s3_key}},
            UpdateExpression="SET #s = :confirmed REMOVE expires_at",
            ConditionExpression="attribute_exists(s3_key) AND #s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":confirmed": {"S": "confirmed"},
                ":pending": {"S": "pending"},
            },
        )
        logger.info("Confirmed reservation for s3_key=%s", s3_key)
        return
    except dynamodb.exceptions.ConditionalCheckFailedException:
        pass

    resp = dynamodb.get_item(
        TableName=RESERVATIONS_TABLE,
        Key={"s3_key": {"S": s3_key}},
        ConsistentRead=True,
    )
    if "Item" in resp:
        logger.info("Reservation already confirmed for s3_key=%s", s3_key)
        return

    _delete_orphan(s3, s3_key)


def _delete_orphan(s3, s3_key: str) -> None:
    try:
        s3.delete_object(Bucket=UPLOADS_BUCKET, Key=s3_key)
        logger.info("Deleted orphaned upload s3_key=%s", s3_key)
    except Exception:
        logger.warning("Failed to delete orphaned upload s3_key=%s", s3_key)
        raise


def _handle_lifecycle_delete(dynamodb, s3_key: str, user_id: str) -> None:
    try:
        dynamodb.transact_write_items(
            TransactItems=[
                {
                    "Delete": {
                        "TableName": RESERVATIONS_TABLE,
                        "Key": {"s3_key": {"S": s3_key}},
                        "ConditionExpression": "attribute_exists(s3_key)",
                    }
                },
                {
                    "Update": {
                        "TableName": USAGE_TABLE,
                        "Key": {"user_id": {"S": user_id}},
                        "UpdateExpression": ("SET active_file_count = active_file_count - :one"),
                        "ExpressionAttributeValues": {":one": {"N": "1"}},
                    }
                },
            ]
        )
        logger.info("Released slot for lifecycle-expired s3_key=%s", s3_key)
    except dynamodb.exceptions.TransactionCanceledException as exc:
        reasons = exc.response.get("CancellationReasons", [])
        if reasons and reasons[0].get("Code") == "ConditionalCheckFailed":
            logger.info("No reservation for expired s3_key=%s", s3_key)
            return
        raise
