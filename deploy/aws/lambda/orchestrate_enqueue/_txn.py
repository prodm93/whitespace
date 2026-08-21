"""DynamoDB transaction helpers for reservation operations."""

from __future__ import annotations

from typing import Any, Literal

ActiveReservationStatus = Literal["pending", "claimed"]


def reserve_txn(
    client: Any,
    usage_table: str,
    jobs_table: str,
    user_id: str,
    job_id: str,
    expires: str,
    condition: str,
    update: str,
    values: dict[str, Any],
    token_suffix: str = "",
) -> None:
    """Atomic usage-update + job-put transaction."""
    kwargs: dict[str, Any] = {
        "TransactItems": [
            {
                "Update": {
                    "TableName": usage_table,
                    "Key": {"user_id": {"S": user_id}},
                    "ConditionExpression": condition,
                    "UpdateExpression": update,
                    "ExpressionAttributeValues": values,
                }
            },
            {
                "Put": {
                    "TableName": jobs_table,
                    "Item": {
                        "job_id": {"S": job_id},
                        "status": {"S": "pending"},
                        "user_id": {"S": user_id},
                        "reservation_status": {"S": "pending"},
                        "reservation_expires_at": {"N": expires},
                    },
                    "ConditionExpression": "attribute_not_exists(job_id)",
                }
            },
        ]
    }
    if token_suffix:
        kwargs["ClientRequestToken"] = f"{job_id}{token_suffix}"
    client.transact_write_items(**kwargs)


def counter_release_item(
    user_id: str,
    job_id: str,
    usage_table: str,
) -> dict[str, Any]:
    """Build a TransactWriteItem that releases one slot from usage counters."""
    return {
        "Update": {
            "TableName": usage_table,
            "Key": {"user_id": {"S": user_id}},
            "ConditionExpression": "contains(pending_job_ids, :jstr)",
            "UpdateExpression": (
                "SET used_count = used_count - :one, "
                "pending_count = pending_count - :one, "
                "version = version + :one "
                "DELETE pending_job_ids :jid"
            ),
            "ExpressionAttributeValues": {
                ":one": {"N": "1"},
                ":jid": {"SS": [job_id]},
                ":jstr": {"S": job_id},
            },
        }
    }


def read_usage(region: str, usage_table: str, user_id: str) -> dict[str, Any] | None:
    """Strongly consistent read of the usage row."""
    import boto3

    return (
        boto3.resource("dynamodb", region_name=region)
        .Table(usage_table)
        .get_item(Key={"user_id": user_id}, ConsistentRead=True)
        .get("Item")
    )


def release_via_transaction(
    client: object,
    user_id: str,
    job_id: str,
    from_status: ActiveReservationStatus,
    usage_table: str,
    jobs_table: str,
) -> None:
    """Atomically release a reservation and decrement usage counters."""
    client.transact_write_items(  # type: ignore[union-attr]
        TransactItems=[
            {
                "Update": {
                    "TableName": jobs_table,
                    "Key": {"job_id": {"S": job_id}},
                    "ConditionExpression": "reservation_status = :st",
                    "UpdateExpression": "SET reservation_status = :released",
                    "ExpressionAttributeValues": {
                        ":st": {"S": from_status},
                        ":released": {"S": "released"},
                    },
                }
            },
            counter_release_item(user_id, job_id, usage_table),
        ]
    )


def release_counter(
    user_id: str,
    job_id: str,
    table: str,
    dynamo: object,
) -> None:
    """Decrement usage counters for a missing job row."""
    from botocore.exceptions import ClientError

    try:
        dynamo.Table(table).update_item(  # type: ignore[union-attr]
            Key={"user_id": user_id},
            ConditionExpression="contains(pending_job_ids, :jstr)",
            UpdateExpression=(
                "SET used_count = used_count - :one, "
                "pending_count = pending_count - :one, "
                "version = version + :one "
                "DELETE pending_job_ids :jid"
            ),
            ExpressionAttributeValues={
                ":one": 1,
                ":jid": {job_id},
                ":jstr": job_id,
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
