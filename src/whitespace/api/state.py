"""Process-wide singleton holding the live :class:`Pipeline`.

The pipeline is built lazily from the current process environment (which
mirrors ``.env``). Submitting credentials via ``POST /api/credentials``
rewrites ``.env``, reloads it into ``os.environ``, and calls
:meth:`AppState.reset` so the next request rebuilds.
"""

from __future__ import annotations

import asyncio
import logging

from whitespace.config import Config
from whitespace.orchestration.pipeline import Pipeline
from whitespace.schemas.profile import ProfessionalProfile

logger = logging.getLogger(__name__)


class AppState:
    def __init__(self) -> None:
        self._pipeline: Pipeline | None = None
        self._profile: ProfessionalProfile | None = None
        self._lock = asyncio.Lock()

    async def get_pipeline(self) -> Pipeline:
        async with self._lock:
            if self._pipeline is None:
                config = Config()
                if not config.openrouter_api_key:
                    raise CredentialsNotSet("OpenRouter API key is not set")
                if not config.neo4j_uri:
                    raise CredentialsNotSet("Neo4j URI is not set")
                logger.info("AppState: building pipeline from current env")
                self._pipeline = Pipeline.from_config(config)
                await self._pipeline.initialise()
            return self._pipeline

    def set_profile(self, profile: ProfessionalProfile) -> None:
        self._profile = profile

    def get_profile(self) -> ProfessionalProfile:
        if self._profile is None:
            raise ProfileNotReady("Profile has not been extracted yet")
        return self._profile

    async def reset(self) -> None:
        async with self._lock:
            if self._pipeline is not None:
                logger.info("AppState: clearing pipeline so next call rebuilds")
                await self._pipeline.close()
                self._pipeline = None
            self._profile = None


class ProfileNotReady(RuntimeError):
    pass


class CredentialsNotSet(RuntimeError):
    pass


app_state = AppState()
