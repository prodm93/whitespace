"""Writes the gap council's mid-run state to local JSON files."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from whitespace.orchestration._gap_council_state import GapCouncilState, dump_mid_state

logger = logging.getLogger(__name__)


class GapSnapshotWriter:
    """Saves one JSON file per run holding the state between the council halves.

    A failed write is logged and swallowed so that a snapshot can never stop
    a run whose research has already been paid for.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    async def save(self, state: GapCouncilState) -> None:
        try:
            run_id = state["run_id"]
            payload = json.dumps(dump_mid_state(state), indent=2)
            await asyncio.to_thread(self._write, run_id, payload)
        except (OSError, KeyError, TypeError, ValueError):
            logger.exception("GapSnapshotWriter: snapshot not saved; run continues")
            return
        logger.info("GapSnapshotWriter: saved snapshot for run %s", run_id)

    def _write(self, run_id: str, payload: str) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        (self._directory / f"{run_id}.json").write_text(payload, encoding="utf-8")
