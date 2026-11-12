"""Process-wide singleton holding the live :class:`Pipeline` and the staged inputs.

One lock guards the pipeline, the count of jobs that use it, and the
credentials. New credentials submitted while a job uses the pipeline wait
and are applied when the last such job ends.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from whitespace.api.routes._credentials_env import persist_env
from whitespace.config import Config
from whitespace.orchestration.pipeline import Pipeline
from whitespace.schemas.profile import ProfessionalProfile
from whitespace.store.base import SessionStore

logger = logging.getLogger(__name__)

SubmitResult = Literal["unchanged", "applied", "waiting"]


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
        self._cond = asyncio.Condition(self._lock)
        self._users = 0
        self._waiting: dict[str, str] | None = None
        self._credentials_error: str | None = None

    @asynccontextmanager
    async def use_pipeline(self) -> AsyncIterator[Pipeline]:
        """Hold the pipeline for one job; waiting credentials are applied after the last job."""
        async with self._cond:
            while self._waiting is not None:
                await self._cond.wait()
            pipeline = await self._build_locked()
            self._users += 1
        try:
            yield pipeline
        finally:
            async with self._cond:
                self._users -= 1
                if self._users == 0 and self._waiting is not None:
                    await self._apply_deferred_locked()
                self._cond.notify_all()

    async def submit_credentials(self, pairs: dict[str, str]) -> SubmitResult:
        """Apply new credentials now, or keep them waiting while a job uses the pipeline."""
        async with self._cond:
            self._credentials_error = None
            if all(os.environ.get(key, "") == value for key, value in pairs.items()):
                self._waiting = None
                self._cond.notify_all()
                return "unchanged"
            if self._users == 0:
                await self._apply_locked(pairs)
                return "applied"
            self._waiting = dict(pairs)
            return "waiting"

    def credentials_error(self) -> str | None:
        return self._credentials_error

    async def _build_locked(self) -> Pipeline:
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

    async def _apply_locked(self, pairs: dict[str, str]) -> None:
        persist_env(pairs)
        await self._switch_locked(pairs)

    async def _apply_deferred_locked(self) -> None:
        """Apply waiting credentials; a failed write keeps the old ones and is reported later."""
        pairs = self._waiting or {}
        try:
            persist_env(pairs)
        except Exception as exc:
            logger.exception("AppState: saving the waiting credentials failed; old ones stay")
            self._credentials_error = str(exc)
            self._waiting = None
            return
        await self._switch_locked(pairs)

    async def _switch_locked(self, pairs: dict[str, str]) -> None:
        os.environ.update(pairs)
        if self._pipeline is not None:
            logger.info("AppState: credentials changed; closing pipeline so the next job rebuilds")
            await self._pipeline.close()
            self._pipeline = None
        self._waiting = None

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


class ProfileNotReady(RuntimeError):
    pass


class CredentialsNotSet(RuntimeError):
    pass


app_state = AppState()
