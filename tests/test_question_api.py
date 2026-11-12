"""The API carries questions and answers: request fields, pending view, job results."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from _question_runs_helpers import make_record
from httpx import ASGITransport, AsyncClient

from whitespace.agents._orchestrator_session import OrchestratorResult
from whitespace.api.app import create_app
from whitespace.api.handlers import register_handlers
from whitespace.api.state import AppState
from whitespace.config import Config
from whitespace.domain import JobStatus
from whitespace.queue.local_queue import LocalAsyncQueue
from whitespace.store.base import GapRun, PendingPause
from whitespace.store.sqlite_store import SqliteSessionStore


class RecordingQueue:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def enqueue(self, job_type: str, payload: dict[str, Any]) -> str:
        self.payloads.append(payload)
        return "job-1"


def _app(tmp_path: Path) -> Any:
    return create_app(Config(_env_file=None, sqlite_db_path=str(tmp_path / "ws.db")))  # type: ignore[call-arg]


async def _client(app: Any) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_orchestrate_queues_answers_and_the_switch(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.state.queue = RecordingQueue()
    answers = [{"question_id": "q-1", "answer": "Pouch cells", "skipped": False}]

    async with await _client(app) as client:
        await client.post(
            "/api/orchestrate",
            json={"intent": "go", "question_answers": answers, "ask_questions": False},
        )
        await client.post("/api/orchestrate", json={"intent": "go"})

    first, second = app.state.queue.payloads
    assert (first["question_answers"], first["ask_questions"]) == (answers, False)
    assert (second["question_answers"], second["ask_questions"]) == (None, None)


def _pause(store_questions: list[Any]) -> PendingPause:
    return PendingPause(
        pause_id="p-1",
        job_id="job-1",
        thread_id="job-1",
        stage="gap",
        questions=store_questions,
        created_at=datetime(2026, 11, 11, tzinfo=UTC),
        computed=True,
    )


@pytest.mark.parametrize("with_gap_run", [False, True])
async def test_latest_runs_shows_the_pending_questions(tmp_path: Path, with_gap_run: bool) -> None:
    app = _app(tmp_path)
    store: SqliteSessionStore = app.state.store
    record = make_record("q-1")
    await store.save_question_records([record])
    await store.update_question_record("q-1", status="answered", answer="Pouch cells")
    await store.save_pending_pause(_pause([record]))
    if with_gap_run:
        await store.save_gap_run(
            GapRun(run_id="gap-1", timestamp=datetime(2026, 11, 1, tzinfo=UTC))
        )

    async with await _client(app) as client:
        body = (await client.get("/api/runs/latest")).json()

    assert body["pending_questions"] == {
        "stage": "gap",
        "editable": False,
        "questions": [
            {
                "question_id": "q-1",
                "question": "Question q-1?",
                "hypothesis": "h",
                "rationale": "r",
                "status": "answered",
                "answer": "Pouch cells",
            }
        ],
    }
    assert (body["gap_run"] is not None) is with_gap_run


async def test_latest_runs_has_no_pending_questions_without_a_pause(tmp_path: Path) -> None:
    async with await _client(_app(tmp_path)) as client:
        body = (await client.get("/api/runs/latest")).json()

    assert body["pending_questions"] is None


class _Pipeline:
    router = None

    async def initialise(self) -> None:
        return None

    async def close(self) -> None:
        return None


async def _settled(queue: LocalAsyncQueue, job_id: str) -> Any:
    for _ in range(200):
        result = await queue.get_status(job_id)
        if result.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return result
        await asyncio.sleep(0.01)
    raise AssertionError("job did not finish")


@pytest.fixture
def handler_queue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[LocalAsyncQueue, Any]:
    state = AppState()
    state.set_store(SqliteSessionStore(tmp_path / "ws.db"))
    monkeypatch.setattr("whitespace.api.state.app_state", state)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("NEO4J_URI", "neo4j://x")
    monkeypatch.setattr("whitespace.api.state.Pipeline.from_config", lambda *_a, **_kw: _Pipeline())
    seen: dict[str, Any] = {}

    async def run(self: Any, intent: str, actions: Any) -> OrchestratorResult:
        seen["session"] = actions.session
        return OrchestratorResult(
            status="awaiting_answers",
            needs=[],
            proposals=[],
            questions=[make_record("q-1")],
            stage="gap",
        )

    monkeypatch.setattr("whitespace.agents.orchestrator_agent.OrchestratorAgent.run", run)
    queue = LocalAsyncQueue()
    register_handlers(queue)
    return queue, seen


async def test_a_job_reads_the_switch_as_on_and_returns_the_questions(handler_queue: Any) -> None:
    queue, seen = handler_queue

    job = await _settled(queue, await queue.enqueue("orchestrate", {"intent": "go"}))

    assert seen["session"].ask_questions is True
    assert seen["session"].question_answers is None
    assert job.result["status"] == "awaiting_answers"
    assert job.result["stage"] == "gap"
    assert job.result["questions"] == [
        {"question_id": "q-1", "question": "Question q-1?", "hypothesis": "h", "rationale": "r"}
    ]


async def test_submitted_answers_reach_the_session_with_blanks_skipped(handler_queue: Any) -> None:
    queue, seen = handler_queue
    answers = [
        {"question_id": "q-1", "answer": "Pouch cells", "skipped": False},
        {"question_id": "q-2", "answer": "   ", "skipped": False},
        {"question_id": "q-3", "answer": "ignored", "skipped": True},
    ]

    await _settled(
        queue,
        await queue.enqueue(
            "orchestrate", {"intent": "go", "question_answers": answers, "ask_questions": False}
        ),
    )

    session = seen["session"]
    assert session.ask_questions is False
    assert [(a.question_id, a.status, a.answer) for a in session.question_answers] == [
        ("q-1", "answered", "Pouch cells"),
        ("q-2", "skipped", ""),
        ("q-3", "skipped", ""),
    ]
