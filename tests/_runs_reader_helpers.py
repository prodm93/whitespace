"""Loading the runs_reader Lambda by file path, and the events its routes receive."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_HANDLER_PATH = (
    Path(__file__).parent.parent / "deploy" / "aws" / "lambda" / "runs_reader" / "handler.py"
)


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("runs_reader_handler", _HANDLER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _event(route: str, job_id: str | None = None, caller: str | None = "user_a") -> dict:
    """An event for ``route``; ``caller`` is the authoriser's user ID, ``None`` for no context."""
    event: dict = {
        "routeKey": route,
        "pathParameters": {"jobId": job_id} if job_id else None,
    }
    if caller is not None:
        event["requestContext"] = {"authorizer": {"lambda": {"user_id": caller}}}
    return event
