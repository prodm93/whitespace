"""Credentials during a run: unchanged keys rebuild nothing, new keys wait for the last job."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from _question_runs_helpers import FakeGapHalves, QuestionsOnlyPipeline, make_record

from whitespace.api.handlers import register_handlers
from whitespace.api.routes import _credentials_env
from whitespace.api.state import AppState
from whitespace.config import Config
from whitespace.domain import JobStatus
from whitespace.orchestration._question_pause import QuestionPauseShell
from whitespace.orchestration._question_runs import QuestionRuns
from whitespace.queue.local_queue import LocalAsyncQueue
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.schemas.question import UserAnswer
from whitespace.store.sqlite_store import SqliteSessionStore


def test_a_failed_write_leaves_the_old_file_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=old\n")
    monkeypatch.setattr(_credentials_env, "ENV_FILE", env)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(_credentials_env.os, "replace", fail)

    with pytest.raises(OSError, match="disk full"):
        _credentials_env.persist_env({"OPENROUTER_API_KEY": "new"})

    assert env.read_text() == "OPENROUTER_API_KEY=old\n"
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


class FakePipeline:
    builds = 0

    def __init__(self) -> None:
        FakePipeline.builds += 1
        self.closed = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def initialise(self) -> None:
        self.started.set()
        await self.release.wait()

    async def close(self) -> None:
        self.closed = True


_OLD = {"OPENROUTER_API_KEY": "old-key", "NEO4J_URI": "neo4j://old"}
_NEW = {"OPENROUTER_API_KEY": "new-key", "NEO4J_URI": "neo4j://new"}


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppState:
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=old-key\nNEO4J_URI=neo4j://old\n")
    monkeypatch.setattr(_credentials_env, "ENV_FILE", env)
    for key, value in _OLD.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        "whitespace.api.state.Pipeline.from_config",
        lambda *_a, **_kw: FakePipeline(),
    )
    return AppState()


async def _built(state: AppState) -> Any:
    async with state.use_pipeline() as pipeline:
        return pipeline


async def test_the_same_credentials_rebuild_nothing(state: AppState, tmp_path: Path) -> None:
    pipeline = await _built(state)
    before = (tmp_path / ".env").stat().st_mtime_ns

    assert await state.submit_credentials(dict(_OLD)) == "unchanged"

    assert await _built(state) is pipeline
    assert not pipeline.closed
    assert (tmp_path / ".env").stat().st_mtime_ns == before


async def test_new_credentials_with_no_job_apply_at_once_and_keep_the_profile(
    state: AppState, tmp_path: Path
) -> None:
    state.set_profile(ProfessionalProfile(hard_skills=["Python"]))
    state.set_profile_paths(["cv.pdf"])
    state.set_pending_ingest("quantum", ["d.pdf"], True)
    old = await _built(state)

    assert await state.submit_credentials(dict(_NEW)) == "applied"

    assert old.closed
    assert "OPENROUTER_API_KEY=new-key" in (tmp_path / ".env").read_text()
    assert os.environ["OPENROUTER_API_KEY"] == "new-key"
    assert await _built(state) is not old
    assert state.get_profile().hard_skills == ["Python"]
    assert state.get_profile_paths() == ["cv.pdf"]
    assert state.get_pending_ingest() == ("quantum", ["d.pdf"], True)


async def _hold(state: AppState, entered: asyncio.Event, release: asyncio.Event) -> Any:
    async with state.use_pipeline() as pipeline:
        entered.set()
        await release.wait()
        return pipeline


async def _open_block(state: AppState) -> tuple[asyncio.Task[Any], asyncio.Event]:
    entered, release = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(_hold(state, entered, release))
    await entered.wait()
    return task, release


async def test_new_credentials_wait_while_a_job_uses_the_pipeline(
    state: AppState, tmp_path: Path
) -> None:
    task, release = await _open_block(state)
    before = (tmp_path / ".env").read_text()

    assert await state.submit_credentials(dict(_NEW)) == "waiting"
    assert (tmp_path / ".env").read_text() == before
    assert os.environ["OPENROUTER_API_KEY"] == "old-key"

    release.set()
    old = await task
    assert old.closed
    assert os.environ["OPENROUTER_API_KEY"] == "new-key"
    assert "OPENROUTER_API_KEY=new-key" in (tmp_path / ".env").read_text()


async def test_a_job_that_enters_while_keys_wait_gets_the_new_pipeline(state: AppState) -> None:
    task, release = await _open_block(state)
    await state.submit_credentials(dict(_NEW))
    second = asyncio.create_task(_built(state))
    await asyncio.sleep(0)
    assert not second.done()

    release.set()
    old = await task

    new = await second
    assert new is not old and not new.closed


async def test_only_the_newest_waiting_credentials_are_applied(state: AppState) -> None:
    task, release = await _open_block(state)
    await state.submit_credentials({**_NEW, "OPENROUTER_API_KEY": "first-new"})
    await state.submit_credentials(dict(_NEW))

    release.set()
    await task

    assert os.environ["OPENROUTER_API_KEY"] == "new-key"


async def test_resubmitting_the_keys_in_use_drops_the_waiting_ones(state: AppState) -> None:
    task, release = await _open_block(state)
    await state.submit_credentials(dict(_NEW))

    assert await state.submit_credentials(dict(_OLD)) == "unchanged"
    release.set()
    old = await task

    assert not old.closed
    assert os.environ["OPENROUTER_API_KEY"] == "old-key"


async def test_a_job_that_fails_still_releases_and_applies(state: AppState) -> None:
    async def failing_job() -> None:
        async with state.use_pipeline():
            await state.submit_credentials(dict(_NEW))
            raise RuntimeError("job failed")

    with pytest.raises(RuntimeError, match="job failed"):
        await failing_job()

    assert os.environ["OPENROUTER_API_KEY"] == "new-key"
    assert state._users == 0


async def test_keys_submitted_during_a_pipeline_build_wait_for_that_job(
    state: AppState, monkeypatch: pytest.MonkeyPatch
) -> None:
    building = FakePipeline()
    building.release.clear()
    monkeypatch.setattr("whitespace.api.state.Pipeline.from_config", lambda *_a, **_kw: building)
    job = asyncio.create_task(_built(state))
    await building.started.wait()

    submit = asyncio.create_task(state.submit_credentials(dict(_NEW)))
    await asyncio.sleep(0)
    assert not submit.done()
    building.release.set()

    assert await submit == "waiting"
    pipeline = await job
    assert pipeline is building


async def test_a_held_job_starts_on_the_old_pipeline_when_waiting_keys_are_dropped(
    state: AppState,
) -> None:
    task, release = await _open_block(state)
    await state.submit_credentials(dict(_NEW))
    waiter = asyncio.create_task(_built(state))
    await asyncio.sleep(0)

    await state.submit_credentials(dict(_OLD))
    held = await waiter
    release.set()
    old = await task

    assert held is old
    assert not old.closed


async def _settled(queue: LocalAsyncQueue, job_id: str) -> Any:
    for _ in range(200):
        result = await queue.get_status(job_id)
        if result.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return result
        await asyncio.sleep(0.01)
    raise AssertionError("job did not finish")


async def test_a_failed_deferred_save_keeps_the_job_result_and_the_old_keys(
    state: AppState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    seen: list[Any] = []

    async def first(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with state.use_pipeline() as pipeline:
            seen.append(pipeline)
            await release.wait()
        return {"done": True}

    async def second(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with state.use_pipeline() as pipeline:
            seen.append(pipeline)
        return {"done": True}

    queue = LocalAsyncQueue()
    queue.register_handler("first", first)
    queue.register_handler("second", second)
    first_id = await queue.enqueue("first", {})
    await asyncio.sleep(0.01)
    assert await state.submit_credentials(dict(_NEW)) == "waiting"
    second_id = await queue.enqueue("second", {})

    def fail(_pairs: dict[str, str]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("whitespace.api.state.persist_env", fail)
    before = (tmp_path / ".env").read_text()
    release.set()

    done = await _settled(queue, first_id)
    assert (done.status, done.result) == (JobStatus.COMPLETED, {"done": True})
    assert (await _settled(queue, second_id)).status == JobStatus.COMPLETED
    assert seen[0] is seen[1]
    assert os.environ["OPENROUTER_API_KEY"] == "old-key"
    assert (tmp_path / ".env").read_text() == before
    assert state.credentials_error() == "disk full"


async def test_after_a_failed_save_the_next_run_is_blocked_until_keys_are_entered(
    state: AppState, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("whitespace.api.state.app_state", state)
    state._credentials_error = "disk full"
    queue = LocalAsyncQueue()
    register_handlers(queue)
    builds = FakePipeline.builds

    job = await _settled(queue, await queue.enqueue("orchestrate", {"intent": "go"}))

    assert job.result["status"] == "blocked"
    assert job.result["reason"] == "Your new keys could not be saved. Enter them again."
    assert FakePipeline.builds == builds
    await state.submit_credentials(dict(_OLD))
    assert state.credentials_error() is None


async def test_a_paused_run_continues_through_the_pipeline_rebuilt_with_the_new_keys(
    state: AppState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SqliteSessionStore(tmp_path / "ws.db")
    await store.save_question_records([make_record("q-1")])
    state.set_store(store)

    def build(config: Config, **_kw: Any) -> QuestionsOnlyPipeline:
        halves = FakeGapHalves([make_record("q-1")])
        shell = QuestionPauseShell(str(tmp_path / "checkpoints.db"))
        runs = QuestionRuns(store, shell, halves, halves)  # type: ignore[arg-type]
        return QuestionsOnlyPipeline(runs, store, key=config.openrouter_api_key, halves=halves)

    monkeypatch.setattr("whitespace.api.state.Pipeline.from_config", build)
    old = await _built(state)
    await old.analyse_gaps_with_questions(
        ProfessionalProfile(), "energy", run_id="job-1", fresh_start=True
    )

    assert await state.submit_credentials(dict(_NEW)) == "applied"

    async with state.use_pipeline() as pipeline:
        resumed = await pipeline.resume_questions(
            [UserAnswer(question_id="q-1", status="answered", answer="Pouch cells")]
        )
    assert (old.closed, old.key, pipeline.key) == (True, "old-key", "new-key")
    assert [n.title for n in resumed.needs] == ["Heat recovery"]
    assert (old.halves.second_answers, len(pipeline.halves.second_answers)) == ([], 1)


async def _post(state: AppState, monkeypatch: pytest.MonkeyPatch, ok: bool, tmp_path: Path) -> Any:
    from httpx import ASGITransport, AsyncClient

    from whitespace.api.app import create_app
    from whitespace.api.routes import credentials

    async def openrouter(_key: str) -> tuple[bool, str | None]:
        return (True, None) if ok else (False, "bad key")

    async def neo4j(*_a: str) -> tuple[bool, str | None]:
        return True, None

    monkeypatch.setattr(credentials, "app_state", state)
    monkeypatch.setattr(credentials, "_check_openrouter", openrouter)
    monkeypatch.setattr(credentials, "_check_neo4j", neo4j)
    body = {"openrouter_api_key": "new-key", "neo4j_uri": "neo4j://new"}
    config = Config(_env_file=None, sqlite_db_path=str(tmp_path / "ws.db"))  # type: ignore[call-arg]
    transport = ASGITransport(app=create_app(config))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return (await client.post("/api/credentials", json=body)).json()


async def test_keys_that_fail_a_check_are_reported_and_not_saved(
    state: AppState, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = (tmp_path / ".env").read_text()

    body = await _post(state, monkeypatch, ok=False, tmp_path=tmp_path)

    assert (body["openrouter_ok"], body["openrouter_error"]) == (False, "bad key")
    assert body["waiting"] is False
    assert (tmp_path / ".env").read_text() == before
    assert os.environ["OPENROUTER_API_KEY"] == "old-key"


async def test_the_response_says_when_new_keys_wait(
    state: AppState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task, release = await _open_block(state)

    body = await _post(state, monkeypatch, ok=True, tmp_path=tmp_path)
    release.set()
    await task

    assert body["waiting"] is True


async def test_an_empty_optional_key_that_is_not_set_counts_as_unchanged(
    state: AppState, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    pipeline = await _built(state)

    assert await state.submit_credentials({**_OLD, "EXA_API_KEY": ""}) == "unchanged"

    assert await _built(state) is pipeline
