"""Process-wide singleton holding live configuration state.

Submitting credentials via ``POST /api/credentials`` rewrites ``.env``,
reloads it into ``os.environ``, and calls :meth:`AppState.reset` so the
next request rebuilds against the new values.
"""

from __future__ import annotations

import asyncio
import logging

from whitespace.config import Config

logger = logging.getLogger(__name__)


class AppState:
    def __init__(self) -> None:
        self._config: Config | None = None
        self._lock = asyncio.Lock()

    async def get_config(self) -> Config:
        async with self._lock:
            if self._config is None:
                self._config = Config()
            return self._config

    async def reset(self) -> None:
        async with self._lock:
            if self._config is not None:
                logger.info("AppState: clearing config so next call rebuilds")
                self._config = None


class CredentialsNotSet(RuntimeError):
    pass


app_state = AppState()
