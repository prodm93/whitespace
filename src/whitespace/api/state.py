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
from whitespace.store.base import SessionStore

logger = logging.getLogger(__name__)


class AppState:
    def __init__(self) -> None:
        self._pipeline: Pipeline | None = None
        self._profile: ProfessionalProfile | None = None
        self._store: SessionStore | None = None
        self._domain: str = ""
        self._doc_paths: list[str] = []
        self._keep_findings: bool = False
        self._profile_paths: list[str] = []
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
                self._pipeline = Pipeline.from_config(config, session_store=self._store)
                await self._pipeline.initialise()
            return self._pipeline

    def set_store(self, store: SessionStore) -> None:
        self._store = store

    def get_store(self) -> SessionStore | None:
        return self._store

    def set_profile(self, profile: ProfessionalProfile) -> None:
        self._profile = profile

    def get_profile(self) -> ProfessionalProfile:
        if self._profile is None:
            raise ProfileNotReady("Profile has not been extracted yet")
        return self._profile

    def set_profile_paths(self, paths: list[str]) -> None:
        self._profile_paths = list(paths)

    def get_profile_paths(self) -> list[str]:
        return list(self._profile_paths)

    def set_pending_ingest(
        self,
        domain: str,
        doc_paths: list[str],
        keep_findings: bool,
    ) -> None:
        """Stage uploads and domain until the gap run ingests them."""
        self._domain = domain
        self._doc_paths = doc_paths
        self._keep_findings = keep_findings

    def get_pending_ingest(self) -> tuple[str, list[str], bool]:
        return self._domain, self._doc_paths, self._keep_findings

    async def reset(self) -> None:
        async with self._lock:
            if self._pipeline is not None:
                logger.info("AppState: clearing pipeline so next call rebuilds")
                await self._pipeline.close()
                self._pipeline = None


class ProfileNotReady(RuntimeError):
    pass


class CredentialsNotSet(RuntimeError):
    pass


app_state = AppState()
