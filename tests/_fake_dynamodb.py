"""In-memory DynamoDB stub for Lambda handler tests.

Supports transact_write_items, query, update_item, and get_item with
condition expressions, SET/REMOVE update expressions, and key
condition matching.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

from _fake_dynamodb_eval import (
    apply_update,
    eval_condition,
    match_key_condition,
    to_ddb,
)

logger = logging.getLogger(__name__)


class _TransactionCancelled(Exception):
    def __init__(self, message: str = "", reasons: list | None = None) -> None:
        super().__init__(message)
        self.response = {"CancellationReasons": reasons or []}


class FakeDynamoDB:
    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict]] = {}
        self.exceptions = MagicMock()
        cond_fail = type("ConditionalCheckFailedException", (Exception,), {})
        self.exceptions.TransactionCanceledException = _TransactionCancelled
        self.exceptions.ConditionalCheckFailedException = cond_fail
        self._cancel_exc = _TransactionCancelled
        self._cond_fail_exc = cond_fail

    def _table(self, name: str) -> dict:
        return self.tables.setdefault(name, {})

    @staticmethod
    def _val(attr: dict) -> Any:
        if "S" in attr:
            return attr["S"]
        if "N" in attr:
            return int(attr["N"])
        return None

    def transact_write_items(self, TransactItems: list[dict]) -> None:
        ops: list[tuple[str, str, dict]] = []
        for idx, item in enumerate(TransactItems):
            try:
                if "Update" in item:
                    ops.append(self._process_update(item["Update"]))
                elif "Put" in item:
                    ops.append(self._process_put(item["Put"]))
                elif "Delete" in item:
                    ops.append(self._process_delete(item["Delete"]))
            except self._cancel_exc:
                reasons = [{"Code": "None"} for _ in TransactItems]
                reasons[idx] = {"Code": "ConditionalCheckFailed"}
                raise self._cancel_exc("Transaction cancelled", reasons) from None

        for action, table, data in ops:
            pk_name = list(data.keys())[0]
            if action == "put":
                self._table(table)[str(data[pk_name])] = data
            elif action == "delete":
                self._table(table).pop(str(data[pk_name]), None)

    def _process_update(self, op: dict) -> tuple[str, str, dict]:
        table = op["TableName"]
        key_raw = op["Key"]
        pk_name = next(iter(key_raw))
        pk_val = self._val(next(iter(key_raw.values())))
        record = self._table(table).get(str(pk_val), {})

        cond = op.get("ConditionExpression", "")
        vals = op.get("ExpressionAttributeValues", {})
        if cond and not eval_condition(cond, record, vals):
            raise self._cancel_exc("condition failed")

        updated = dict(record)
        updated[pk_name] = pk_val
        apply_update(op.get("UpdateExpression", ""), updated, vals)
        return ("put", table, updated)

    def _process_put(self, op: dict) -> tuple[str, str, dict]:
        rec: dict[str, Any] = {}
        for k, v in op["Item"].items():
            rec[k] = self._val(v)
        return ("put", op["TableName"], rec)

    def _process_delete(self, op: dict) -> tuple[str, str, dict]:
        table = op["TableName"]
        key_raw = op["Key"]
        pk_name = next(iter(key_raw))
        pk_val = self._val(next(iter(key_raw.values())))
        record = self._table(table).get(str(pk_val))

        cond = op.get("ConditionExpression", "")
        e_vals = op.get("ExpressionAttributeValues", {})
        e_names = op.get("ExpressionAttributeNames", {})
        if cond and (record is None or not eval_condition(cond, record, e_vals, e_names)):
            raise self._cancel_exc("condition failed")
        return ("delete", table, {pk_name: pk_val})

    def query(self, **kwargs: Any) -> dict:
        table = self._table(kwargs["TableName"])
        e_vals = kwargs.get("ExpressionAttributeValues", {})
        e_names = kwargs.get("ExpressionAttributeNames", {})
        kce = kwargs.get("KeyConditionExpression", "")
        fe = kwargs.get("FilterExpression", "")

        items = []
        for record in table.values():
            if not match_key_condition(kce, record, e_vals):
                continue
            if fe and not eval_condition(fe, record, e_vals, e_names):
                continue
            items.append({k: to_ddb(v) for k, v in record.items()})
        return {"Items": items}

    def update_item(self, **kwargs: Any) -> None:
        table_name = kwargs["TableName"]
        key_raw = kwargs["Key"]
        pk_name = next(iter(key_raw))
        pk_val = self._val(next(iter(key_raw.values())))
        record = self._table(table_name).get(str(pk_val))

        cond = kwargs.get("ConditionExpression", "")
        e_vals = kwargs.get("ExpressionAttributeValues", {})
        e_names = kwargs.get("ExpressionAttributeNames", {})

        if cond:
            if record is None:
                raise self._cond_fail_exc("item not found")
            if not eval_condition(cond, record, e_vals, e_names):
                raise self._cond_fail_exc("condition failed")

        if record is None:
            record = {pk_name: pk_val}
            self._table(table_name)[str(pk_val)] = record

        apply_update(
            kwargs.get("UpdateExpression", ""),
            record,
            e_vals,
            e_names,
        )

    def get_item(self, **kwargs: Any) -> dict:
        table_name = kwargs["TableName"]
        key_raw = kwargs["Key"]
        pk_val = self._val(next(iter(key_raw.values())))
        record = self._table(table_name).get(str(pk_val))
        if record is None:
            return {}
        return {"Item": {k: to_ddb(v) for k, v in record.items()}}
