from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from whitespace.schemas.gap import UnmetNeed
from whitespace.schemas.idea import IdeationProposal
from whitespace.schemas.research import RawFinding
from whitespace.store import _dynamo_items as items
from whitespace.store.base import GapRun, IdeaRun, SessionStore

logger = logging.getLogger(__name__)


class DynamoSessionStore(SessionStore):
    """DynamoDB-backed session store for SaaS mode."""

    def __init__(self, table_name: str, region: str) -> None:
        import boto3

        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    async def _put(self, item: dict[str, object]) -> None:
        await asyncio.to_thread(self._table.put_item, Item=item)

    async def _query(self, pk: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        kwargs: dict[str, object] = {
            "KeyConditionExpression": Key("pk").eq(pk),
            "ScanIndexForward": False,
        }
        if limit is not None:
            kwargs["Limit"] = limit
        response = await asyncio.to_thread(self._table.query, **kwargs)
        return cast("list[dict[str, Any]]", response.get("Items", []))

    async def save_gap_run(self, run: GapRun) -> None:
        await self._put(items.gap_run_to_item(run))

    async def save_idea_run(self, run: IdeaRun) -> None:
        await self._put(items.idea_run_to_item(run))

    async def list_gap_runs(self) -> list[GapRun]:
        rows = await self._query(items.GAPRUN_PK)
        return [items.item_to_gap_run(r) for r in rows]

    async def list_idea_runs(self, gap_run_id: str | None = None) -> list[IdeaRun]:
        rows = await self._query(items.IDEARUN_PK)
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
        rows = await self._query(items.GAPRUN_PK)
        needs: list[UnmetNeed] = []
        for row in rows:
            needs.extend(items.needs_from_gap_run_item(row))
        return needs

    async def get_all_previous_proposals(self) -> list[IdeationProposal]:
        rows = await self._query(items.IDEARUN_PK)
        proposals: list[IdeationProposal] = []
        for row in rows:
            proposals.extend(items.proposals_from_idea_run_item(row))
        return proposals

    async def get_latest_gap_run(self) -> GapRun | None:
        rows = await self._query(items.GAPRUN_PK, limit=1)
        return items.item_to_gap_run(rows[0]) if rows else None

    async def save_raw_findings(self, run_id: str, findings: list[RawFinding]) -> None:
        if not findings:
            return

        def _write_batch() -> None:
            with self._table.batch_writer() as batch:
                for finding in findings:
                    batch.put_item(Item=items.finding_to_item(run_id, finding))

        await asyncio.to_thread(_write_batch)
        logger.info("DynamoSessionStore: saved %d raw findings for run %s", len(findings), run_id)

    async def list_raw_findings(self, run_id: str | None = None) -> list[RawFinding]:
        rows = await self._query(items.FINDINGS_PK)
        if run_id is not None:
            rows = [r for r in rows if r.get("run_id") == run_id]
        return [items.item_to_finding(r) for r in rows]

    async def save_discards(self, run_id: str, kind: str, entries: list[dict[str, str]]) -> None:
        if not entries:
            return

        def _write_batch() -> None:
            with self._table.batch_writer() as batch:
                for entry in entries:
                    batch.put_item(Item=items.discard_to_item(run_id, kind, entry))

        await asyncio.to_thread(_write_batch)
        logger.info("DynamoSessionStore: saved %d %s discards", len(entries), kind)

    async def list_discards(self, kind: str | None = None) -> list[dict[str, str]]:
        kinds = (kind,) if kind is not None else items.DISCARD_KINDS
        rows: list[dict[str, Any]] = []
        for one_kind in kinds:
            rows.extend(await self._query(items.discard_pk(one_kind)))
        rows.sort(key=lambda r: r["sk"], reverse=True)
        return [items.item_to_discard(r) for r in rows]
