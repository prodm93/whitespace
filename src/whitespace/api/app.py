from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from whitespace.config import Config
from whitespace.domain import IngestResult
from whitespace.observability.metrics import MetricsEmitter
from whitespace.queue.base import JobQueue
from whitespace.store.base import SessionStore

if TYPE_CHECKING:
    from whitespace.queue.local_queue import LocalAsyncQueue

logger = logging.getLogger(__name__)


def create_app(config: Config | None = None) -> FastAPI:
    """Build and return a configured FastAPI application.

    Wires the correct JobQueue, MetricsEmitter, and middleware
    implementations based on ``config.mode``.
    """
    if config is None:
        config = Config()

    from whitespace.observability.langsmith import configure_tracing_env

    configure_tracing_env(config)

    app = FastAPI(title="WhiteSpace", version="0.1.0")
    app.state.config = config
    app.state.queue = _build_queue(config)
    app.state.metrics = _build_metrics(config)
    app.state.store = _build_store(config)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://localhost:3000",
            "http://localhost:8000",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _mount_routes(app)

    logger.info("WhiteSpace app created in %s mode", config.mode)
    return app


def _build_queue(config: Config) -> JobQueue:
    if config.mode == "byok":
        from whitespace.queue.local_queue import LocalAsyncQueue

        queue = LocalAsyncQueue()
        _register_handlers(queue)
        return queue

    from whitespace.queue.sqs_queue import SqsJobQueue

    return SqsJobQueue(config)


def _register_handlers(queue: LocalAsyncQueue) -> None:
    from typing import Any

    from whitespace.api.state import (
        CredentialsNotSet,
        ProfileNotReady,
        app_state,
    )

    async def handle_ingest(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            pipeline = await app_state.get_pipeline()
        except CredentialsNotSet as exc:
            raise RuntimeError(str(exc)) from exc

        profile_paths: list[str] = payload.get("profile_paths", [])
        domain_paths: list[str] = payload.get("domain_paths", [])

        if profile_paths:
            profile = await pipeline.extract_profile(profile_paths)
            app_state.set_profile(profile)

        all_paths = profile_paths + domain_paths
        if all_paths:
            result = await pipeline.ingest(all_paths)
        else:
            result = IngestResult(documents_processed=0)

        return {"documents_processed": result.documents_processed}

    async def handle_gaps(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            pipeline = await app_state.get_pipeline()
        except CredentialsNotSet as exc:
            raise RuntimeError(str(exc)) from exc
        try:
            profile = app_state.get_profile()
        except ProfileNotReady as exc:
            raise RuntimeError(str(exc)) from exc
        needs = await pipeline.analyse_gaps(profile)
        return {"needs": [n.model_dump() for n in needs]}

    async def handle_ideation(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            pipeline = await app_state.get_pipeline()
        except CredentialsNotSet as exc:
            raise RuntimeError(str(exc)) from exc
        try:
            profile = app_state.get_profile()
        except ProfileNotReady as exc:
            raise RuntimeError(str(exc)) from exc
        proposals = await pipeline.ideate(
            payload["selected_needs"],
            profile,
        )
        return {"proposals": [p.model_dump() for p in proposals]}

    queue.register_handler("ingest", handle_ingest)
    queue.register_handler("gap_analysis", handle_gaps)
    queue.register_handler("ideation", handle_ideation)


def _build_metrics(config: Config) -> MetricsEmitter:
    if config.mode == "byok":
        from whitespace.observability.local_metrics import LocalMetricsEmitter

        return LocalMetricsEmitter()

    from whitespace.observability.cloudwatch_metrics import (
        CloudWatchMetricsEmitter,
    )

    return CloudWatchMetricsEmitter(namespace="whitespace", region=config.aws_region)


def _build_store(config: Config) -> SessionStore:
    if config.mode == "byok":
        from pathlib import Path

        from whitespace.store.sqlite_store import SqliteSessionStore

        db_path = Path(config.sqlite_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteSessionStore(db_path)

    from whitespace.store.noop_store import NoopSessionStore

    return NoopSessionStore()


def _mount_routes(app: FastAPI) -> None:
    from whitespace.api.routes import (
        credentials,
        gaps,
        ideate,
        ingest,
        jobs,
        profile,
        query,
    )

    app.include_router(ingest.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(gaps.router, prefix="/api")
    app.include_router(ideate.router, prefix="/api")
    app.include_router(query.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(credentials.router, prefix="/api")
