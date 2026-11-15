"""An in-memory sessions table that several ``DynamoSessionStore`` objects share."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class FakeSessionsTable:
    """Holds items by ``pk`` and ``sk`` and answers a query on ``pk``, as DynamoDB does."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def put_item(self, *, Item: dict[str, Any]) -> None:
        self.items = [i for i in self.items if (i["pk"], i["sk"]) != (Item["pk"], Item["sk"])]
        self.items.append(dict(Item))

    def query(
        self,
        *,
        KeyConditionExpression: Any,
        ScanIndexForward: bool = True,
        Limit: int | None = None,
    ) -> dict[str, Any]:
        key, value = KeyConditionExpression.get_expression()["values"]
        assert key.name == "pk", "the store queries on the partition key only"
        rows = sorted(
            (i for i in self.items if i["pk"] == value),
            key=lambda i: i["sk"],
            reverse=not ScanIndexForward,
        )
        return {"Items": rows if Limit is None else rows[:Limit]}

    def batch_writer(self) -> _BatchWriter:
        return _BatchWriter(self)


class _BatchWriter:
    def __init__(self, table: FakeSessionsTable) -> None:
        self._table = table

    def __enter__(self) -> _BatchWriter:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def put_item(self, *, Item: dict[str, Any]) -> None:
        self._table.put_item(Item=Item)


def install_sessions_table(monkeypatch: Any) -> FakeSessionsTable:
    """Make every ``boto3.resource("dynamodb")`` hand out the one fake table."""
    import boto3

    table = FakeSessionsTable()
    resource = SimpleNamespace(Table=lambda _name: table)
    monkeypatch.setattr(boto3, "resource", lambda *_a, **_kw: resource)
    return table
