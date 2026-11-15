"""Loading a module by its file path, and driving handlers that use the current event loop."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any


def load_module(name: str, path: Path) -> ModuleType:
    """Load the module at ``path`` under ``name``, without putting its folder on the path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def own_event_loop() -> Iterator[None]:
    """Make a new event loop current for code that calls ``asyncio.get_event_loop()``."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def call_with_body(module: Any, body: Any) -> tuple[int, dict]:
    """Call ``module.handler`` with ``body`` (JSON-encoded unless it is already a string)."""
    raw = body if isinstance(body, str) else json.dumps(body)
    result = module.handler({"body": raw}, None)
    return result["statusCode"], json.loads(result["body"])
