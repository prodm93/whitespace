"""A continue that fails inside the paused run fails its job and keeps the pause."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from _question_runs_helpers import QuestionsOnlyPipeline, make_record, make_runs

from whitespace.api.handlers import register_handlers
from whitespace.api.state import AppState
from whitespace.domain import JobStatus
from whitespace.queue.local_queue import LocalAsyncQueue
from whitespace.store.sqlite_store import SqliteSessionStore


class _Router:
    def __init__(self, tool_name: str) -> None:
        self.replies = [
            {"content": "", "tool_calls": [{"id": "0", "name": tool_name, "arguments": {}}]},
            {"content": "done", "tool_calls": []},
        ]

    async def call(self, **_kw: Any) -> dict[str, Any]:
        return self.replies.pop(0)


async def _settled(queue: LocalAsyncQueue, job_id: str) -> Any:
    for _ in range(200):
        result = await queue.get_status(job_id)
        if result.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return result
        await asyncio.sleep(0.01)
    raise AssertionError("job did not finish")


async def test_a_failed_continue_through_the_orchestrator_fails_the_job_and_keeps_the_pause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SqliteSessionStore(tmp_path / "ws.db")
    runs, _, halves, _ = await make_runs(tmp_path, [make_record("q-1")], store=store, failures=1)
    await runs.start("gap", "job-1", {"run_id": "job-1"})
    pipeline = QuestionsOnlyPipeline(runs, store, router=_Router("submit_question_answers"))
    state = AppState()
    state.set_store(store)
    monkeypatch.setattr("whitespace.api.state.app_state", state)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("NEO4J_URI", "neo4j://x")
    monkeypatch.setattr("whitespace.api.state.Pipeline.from_config", lambda *_a, **_kw: pipeline)
    queue = LocalAsyncQueue()
    register_handlers(queue)
    answers = [{"question_id": "q-1", "answer": "Pouch cells", "skipped": False}]

    job = await _settled(
        queue,
        await queue.enqueue("orchestrate", {"intent": "Continue", "question_answers": answers}),
    )

    assert job.status == JobStatus.FAILED
    assert "second half failed" in (job.error or "")
    assert halves.second_answers == [
        [{"question_id": "q-1", "status": "answered", "answer": "Pouch cells"}]
    ]
    assert await store.get_pending_pause() is not None
