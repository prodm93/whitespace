"""Issues presigned S3 POST policies for user file uploads.

Receives POST /api/upload-url from API Gateway (authenticated); checks
the caller's tier against file count and size limits; generates a
presigned POST policy for the uploads bucket under uploads/{user_id}/.
The frontend POSTs bytes directly to S3 and passes the returned S3 keys
in the orchestrate payload.

POST policy (not PUT) is required so that content-length-range can be
enforced as a policy condition -- the only server-side file-size guard
available at upload time.
"""

from __future__ import annotations

import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")

_TIER_LIMITS: dict[str, dict] = {
    "free": {"max_files": 3, "max_bytes": 50 * 1024 * 1024},
    "standard": {"max_files": 10, "max_bytes": 200 * 1024 * 1024},
    "pro": {"max_files": 50, "max_bytes": 1024 * 1024 * 1024},
}
_DEFAULT_TIER = "free"


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
        return _response(
            403,
            {
                "error": (
                    f"File exceeds {limits['max_bytes'] // (1024 * 1024)} MB limit for {tier} tier"
                )
            },
        )

    file_count = _count_user_files(user_id)
    if file_count >= limits["max_files"]:
        return _response(
            403,
            {"error": f"File limit of {limits['max_files']} files reached for {tier} tier"},
        )

    key = f"uploads/{user_id}/{uuid.uuid4().hex}_{filename}"
    presigned = _generate_presigned_post(key, limits["max_bytes"])
    logger.info("Presigned POST issued for user=%s key=%s", user_id, key)
    return _response(200, {"s3_key": key, "presigned_post": presigned})


def _count_user_files(user_id: str) -> int:
    import boto3

    s3 = boto3.client("s3", region_name=AWS_REGION)
    resp = s3.list_objects_v2(Bucket=UPLOADS_BUCKET, Prefix=f"uploads/{user_id}/")
    return int(resp.get("KeyCount", 0))


def _generate_presigned_post(key: str, max_bytes: int) -> dict:
    import boto3

    s3 = boto3.client("s3", region_name=AWS_REGION)
    return s3.generate_presigned_post(
        Bucket=UPLOADS_BUCKET,
        Key=key,
        Conditions=[
            ["content-length-range", 1, max_bytes],
        ],
        ExpiresIn=900,
    )


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
