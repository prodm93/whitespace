from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.research import RawFinding
from whitespace.store import _dynamo_items as items
from whitespace.store.base import GapRun, IdeaRun, SessionStore
from whitespace.tenant import require_tenant_id

logger = logging.getLogger(__name__)

_MAX_PAGES = 1000


class DynamoSessionStore(SessionStore):
    """DynamoDB-backed session store for SaaS mode, bound to one tenant's partition."""

    def __init__(self, table_name: str, region: str, *, owner: str) -> None:
        self._owner = require_tenant_id(owner)
        import boto3

        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    async def _put(self, item: dict[str, object]) -> None:
        await asyncio.to_thread(self._table.put_item, Item=item)

    async def _query(self, pk: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        """The rows of ``pk`` in descending sort-key order: every page, or the first ``limit``.

        A history longer than ``_MAX_PAGES`` pages raises ``RuntimeError`` rather than being
        cut short.
        """
        from boto3.dynamodb.conditions import Key

        kwargs: dict[str, object] = {
            "KeyConditionExpression": Key("pk").eq(pk),
            "ScanIndexForward": False,
        }
        if limit is not None:
            kwargs["Limit"] = limit
        rows: list[dict[str, Any]] = []
        for _ in range(_MAX_PAGES):
            response = await asyncio.to_thread(self._table.query, **kwargs)
            rows.extend(cast("list[dict[str, Any]]", response.get("Items", [])))
            last_key = response.get("LastEvaluatedKey")
            if limit is not None or not last_key:
                return rows
            kwargs["ExclusiveStartKey"] = last_key
        raise RuntimeError(f"The history of {pk} has more than {_MAX_PAGES} pages")

    async def _put_run(self, index_pk: str, item: dict[str, Any]) -> None:
        """Put a run row under the sort key that the run ID's index row holds.

        The first save of a run ID writes the index row; a later save reads it and
        overwrites the same run row, so a repeated save leaves one run.
        """
        from botocore.exceptions import ClientError

        index = items.run_index_item(index_pk, item["run_id"], item["sk"])
        try:
            await asyncio.to_thread(
                self._table.put_item, Item=index, ConditionExpression="attribute_not_exists(pk)"
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            response = await asyncio.to_thread(
                self._table.get_item,
                Key={"pk": index["pk"], "sk": index["sk"]},
                ConsistentRead=True,
            )
            item = {**item, "sk": response["Item"]["run_sk"]}
        await self._put(item)

    async def save_gap_run(self, run: GapRun) -> None:
        item = items.gap_run_to_item(self._owner, run)
        await self._put_run(items.gap_run_index_pk(self._owner), item)

    async def save_idea_run(self, run: IdeaRun) -> None:
        item = items.idea_run_to_item(self._owner, run)
        await self._put_run(items.idea_run_index_pk(self._owner), item)

    async def list_gap_runs(self) -> list[GapRun]:
        rows = await self._query(items.gap_run_pk(self._owner))
        return [items.item_to_gap_run(r) for r in rows]

    async def list_idea_runs(self, gap_run_id: str | None = None) -> list[IdeaRun]:
        rows = await self._query(items.idea_run_pk(self._owner))
        runs = [items.item_to_idea_run(r) for r in rows]
        if gap_run_id is not None:
            runs = [r for r in runs if r.gap_run_id == gap_run_id]
        return runs

    async def get_gap_run(self, run_id: str) -> GapRun | None:
        for run in await self.list_gap_runs():
            if run.run_id == run_id:
                return run
        return None

    async def get_idea_run(self, run_id: str) -> IdeaRun | None:
        for run in await self.list_idea_runs():
            if run.run_id == run_id:
                return run
        return None

    async def get_all_previous_needs(self) -> list[UnmetNeed]:
        runs = await self.list_gap_runs()
        return [need for run in runs for need in run.needs]

    async def get_all_previous_proposals(self) -> list[IdeationProposal]:
        rows = await self._query(items.idea_run_pk(self._owner))
        proposals: list[IdeationProposal] = []
        for row in rows:
            proposals.extend(items.proposals_from_idea_run_item(row))
        return proposals

    async def get_latest_gap_run(self) -> GapRun | None:
        rows = await self._query(items.gap_run_pk(self._owner), limit=1)
        return items.item_to_gap_run(rows[0]) if rows else None

    async def save_raw_findings(self, run_id: str, findings: list[RawFinding]) -> None:
        if not findings:
            return

        def _write_batch() -> None:
            with self._table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
                for finding in findings:
                    batch.put_item(Item=items.finding_to_item(self._owner, run_id, finding))

        await asyncio.to_thread(_write_batch)
        logger.info("DynamoSessionStore: saved %d raw findings for run %s", len(findings), run_id)

    async def list_raw_findings(self, run_id: str | None = None) -> list[RawFinding]:
        rows = await self._query(items.findings_pk(self._owner))
        if run_id is not None:
            rows = [r for r in rows if r.get("run_id") == run_id]
        rows.sort(key=lambda r: r["found_at"], reverse=True)
        return [items.item_to_finding(r) for r in rows]

    async def save_discards(self, run_id: str, kind: str, entries: list[dict[str, str]]) -> None:
        if not entries:
            return

        def _write_batch() -> None:
            with self._table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
                for entry in entries:
                    batch.put_item(Item=items.discard_to_item(self._owner, run_id, kind, entry))

        await asyncio.to_thread(_write_batch)
        logger.info("DynamoSessionStore: saved %d %s discards", len(entries), kind)

    async def list_discards(self, kind: str | None = None) -> list[dict[str, str]]:
        kinds = (kind,) if kind is not None else items.DISCARD_KINDS
        rows: list[dict[str, Any]] = []
        for one_kind in kinds:
            rows.extend(await self._query(items.discard_pk(self._owner, one_kind)))
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [items.item_to_discard(r) for r in rows]
