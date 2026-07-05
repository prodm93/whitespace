import logging

from fastapi import FastAPI

from whitespace.config import Config
from whitespace.observability.metrics import MetricsEmitter
from whitespace.queue.base import JobQueue
from whitespace.store.base import SessionStore

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

    _mount_routes(app)

    logger.info("WhiteSpace app created in %s mode", config.mode)
    return app


def _build_queue(config: Config) -> JobQueue:
    if config.mode == "byok":
        from whitespace.queue.local_queue import LocalAsyncQueue

        return LocalAsyncQueue()

    from whitespace.queue.sqs_queue import SqsJobQueue

    return SqsJobQueue(config)


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
