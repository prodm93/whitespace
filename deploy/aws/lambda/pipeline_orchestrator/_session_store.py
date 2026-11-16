"""The session store of one run, bound to the tenant of that run."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from whitespace.config import Config

if TYPE_CHECKING:
    from whitespace.store.base import SessionStore

logger = logging.getLogger(__name__)


def _build_session_store(config: Config, owner: str) -> SessionStore:
    if config.sessions_table:
        from whitespace.store.dynamo_store import DynamoSessionStore

        return DynamoSessionStore(config.sessions_table, config.aws_region, owner=owner)
    logger.warning("SESSIONS_TABLE not set; session persistence disabled")
    from whitespace.store.noop_store import NoopSessionStore

    return NoopSessionStore()
