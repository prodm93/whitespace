"""An in-memory sessions table that several ``DynamoSessionStore`` objects share."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from botocore.exceptions import ClientError


def _key(item: dict[str, Any]) -> tuple[Any, Any]:
    return (item["pk"], item["sk"])


class FakeSessionsTable:
    """Holds items by ``pk`` and ``sk`` and answers a query on ``pk``, as DynamoDB does.

    A query answers at most ``page_size`` rows when one is set, with ``LastEvaluatedKey``
    when rows are left. ``query_calls`` counts the query calls.
    """

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.page_size: int | None = None
        self.query_calls = 0

    def put_item(self, *, Item: dict[str, Any], ConditionExpression: str | None = None) -> None:
        if ConditionExpression is not None:
            assert ConditionExpression == "attribute_not_exists(pk)", "unsupported condition"
            if any(_key(i) == _key(Item) for i in self.items):
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}},
                    "PutItem",
                )
        self.items = [i for i in self.items if _key(i) != _key(Item)]
        self.items.append(dict(Item))

    def get_item(self, *, Key: dict[str, Any], ConsistentRead: bool = False) -> dict[str, Any]:
        for item in self.items:
            if _key(item) == _key(Key):
                return {"Item": dict(item)}
        return {}

    def query(
        self,
        *,
        KeyConditionExpression: Any,
        ScanIndexForward: bool = True,
        Limit: int | None = None,
        ExclusiveStartKey: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.query_calls += 1
        key, value = KeyConditionExpression.get_expression()["values"]
        assert key.name == "pk", "the store queries on the partition key only"
        rows = sorted(
            (i for i in self.items if i["pk"] == value),
            key=lambda i: i["sk"],
            reverse=not ScanIndexForward,
        )
        if ExclusiveStartKey is not None:
            start = [_key(i) for i in rows].index(_key(ExclusiveStartKey)) + 1
            rows = rows[start:]
        size = min(n for n in (Limit, self.page_size, len(rows)) if n is not None)
        page = rows[:size]
        answer: dict[str, Any] = {"Items": page}
        if len(rows) > size and Limit is None:
            answer["LastEvaluatedKey"] = {"pk": page[-1]["pk"], "sk": page[-1]["sk"]}
        return answer

    def batch_writer(self, overwrite_by_pkeys: list[str] | None = None) -> _BatchWriter:
        return _BatchWriter(self, overwrite_by_pkeys)


class _BatchWriter:
    """Buffers the puts of one batch; two items with one key fail unless they may overwrite."""

    def __init__(self, table: FakeSessionsTable, overwrite_by_pkeys: list[str] | None) -> None:
        self._table = table
        self._overwrite = overwrite_by_pkeys == ["pk", "sk"]
        self._buffer: list[dict[str, Any]] = []

    def __enter__(self) -> _BatchWriter:
        return self

    def __exit__(self, *_exc: object) -> None:
        for item in self._buffer:
            self._table.put_item(Item=item)

    def put_item(self, *, Item: dict[str, Any]) -> None:
        if any(_key(i) == _key(Item) for i in self._buffer):
            if not self._overwrite:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ValidationException",
                            "Message": "Provided list of item keys contains duplicates",
                        }
                    },
                    "BatchWriteItem",
                )
            self._buffer = [i for i in self._buffer if _key(i) != _key(Item)]
        self._buffer.append(dict(Item))


def install_sessions_table(monkeypatch: Any) -> FakeSessionsTable:
    """Make every ``boto3.resource("dynamodb")`` hand out the one fake table."""
    import boto3

    table = FakeSessionsTable()
    resource = SimpleNamespace(Table=lambda _name: table)
    monkeypatch.setattr(boto3, "resource", lambda *_a, **_kw: resource)
    return table
