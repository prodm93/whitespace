"""Presigned S3 POST with atomic file-slot reservation."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")
USAGE_TABLE = os.environ.get("USAGE_TABLE", "")
RESERVATIONS_TABLE = os.environ.get("RESERVATIONS_TABLE", "")

_TIER_LIMITS: dict[str, dict] = {
    "free": {"max_files": 3, "max_bytes": 50 * 1024 * 1024},
    "standard": {"max_files": 10, "max_bytes": 200 * 1024 * 1024},
    "pro": {"max_files": 50, "max_bytes": 1024 * 1024 * 1024},
}
_DEFAULT_TIER = "free"
_RESERVATION_TTL = 3600


def handler(event: dict, context: object) -> dict:
    auth = ((event.get("requestContext") or {}).get("authorizer") or {}).get("lambda") or {}
    user_id = auth.get("user_id", "")
    tier = auth.get("tier", _DEFAULT_TIER)

    if not user_id:
        return _response(401, {"error": "Unauthenticated"})

    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Invalid JSON body"})

    filename = body.get("filename", "upload")
    file_size = int(body.get("file_size", 0))

    limits = _TIER_LIMITS.get(tier, _TIER_LIMITS[_DEFAULT_TIER])
    if file_size > limits["max_bytes"]:
        mb = limits["max_bytes"] // (1024 * 1024)
        return _response(403, {"error": f"File exceeds {mb} MB limit for {tier} tier"})

    import boto3

    dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)
    _reclaim_expired(dynamodb, user_id)

    key = f"uploads/{user_id}/{uuid.uuid4().hex}_{filename}"
    if not _reserve_slot(dynamodb, user_id, key, limits["max_files"]):
        return _response(
            403,
            {"error": f"File limit of {limits['max_files']} files reached for {tier} tier"},
        )

    try:
        presigned = _generate_presigned_post(key, limits["max_bytes"])
    except Exception:
        _release_slot(dynamodb, user_id, key)
        return _response(500, {"error": "Failed to generate upload URL"})

    logger.info("Presigned POST issued for user=%s key=%s", user_id, key)
    return _response(200, {"s3_key": key, "presigned_post": presigned})


def _reclaim_expired(dynamodb, user_id: str) -> None:
    now_epoch = str(int(time.time()))

    resp = dynamodb.query(
        TableName=RESERVATIONS_TABLE,
        IndexName="user_id-index",
        KeyConditionExpression="user_id = :uid",
        FilterExpression="#s = :pending AND expires_at <= :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":uid": {"S": user_id},
            ":pending": {"S": "pending"},
            ":now": {"N": now_epoch},
        },
    )

    for item in resp.get("Items", []):
        s3_key = item["s3_key"]["S"]
        try:
            dynamodb.transact_write_items(
                TransactItems=[
                    {
                        "Delete": {
                            "TableName": RESERVATIONS_TABLE,
                            "Key": {"s3_key": {"S": s3_key}},
                            "ConditionExpression": "#s = :pending",
                            "ExpressionAttributeNames": {"#s": "status"},
                            "ExpressionAttributeValues": {
                                ":pending": {"S": "pending"},
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": USAGE_TABLE,
                            "Key": {"user_id": {"S": user_id}},
                            "UpdateExpression": "SET active_file_count = active_file_count - :one",
                            "ExpressionAttributeValues": {":one": {"N": "1"}},
                        }
                    },
                ]
            )
            logger.info("Reclaimed expired reservation s3_key=%s", s3_key)
        except dynamodb.exceptions.TransactionCanceledException:
            pass


def _reserve_slot(dynamodb, user_id: str, s3_key: str, max_files: int) -> bool:
    ttl = str(int(time.time()) + _RESERVATION_TTL)

    try:
        dynamodb.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": USAGE_TABLE,
                        "Key": {"user_id": {"S": user_id}},
                        "UpdateExpression": (
                            "SET active_file_count = if_not_exists(active_file_count, :zero) + :one"
                        ),
                        "ConditionExpression": (
                            "attribute_not_exists(active_file_count) OR active_file_count < :max"
                        ),
                        "ExpressionAttributeValues": {
                            ":zero": {"N": "0"},
                            ":one": {"N": "1"},
                            ":max": {"N": str(max_files)},
                        },
                    }
                },
                {
                    "Put": {
                        "TableName": RESERVATIONS_TABLE,
                        "Item": {
                            "s3_key": {"S": s3_key},
                            "user_id": {"S": user_id},
                            "status": {"S": "pending"},
                            "expires_at": {"N": ttl},
                        },
                    }
                },
            ]
        )
        return True
    except dynamodb.exceptions.TransactionCanceledException:
        return False


def _release_slot(dynamodb, user_id: str, s3_key: str) -> None:
    try:
        dynamodb.transact_write_items(
            TransactItems=[
                {
                    "Delete": {
                        "TableName": RESERVATIONS_TABLE,
                        "Key": {"s3_key": {"S": s3_key}},
                    }
                },
                {
                    "Update": {
                        "TableName": USAGE_TABLE,
                        "Key": {"user_id": {"S": user_id}},
                        "UpdateExpression": "SET active_file_count = active_file_count - :one",
                        "ExpressionAttributeValues": {":one": {"N": "1"}},
                    }
                },
            ]
        )
    except Exception:
        logger.warning("Failed to release slot user=%s key=%s", user_id, s3_key)


def _generate_presigned_post(key: str, max_bytes: int) -> dict:
    import boto3

    s3 = boto3.client("s3", region_name=AWS_REGION)
    return s3.generate_presigned_post(
        Bucket=UPLOADS_BUCKET,
        Key=key,
        Conditions=[["content-length-range", 1, max_bytes]],
        ExpiresIn=900,
    )


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
