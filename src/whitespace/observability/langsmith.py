"""LangSmith tracing with three-tier privacy consent.

* ``full``           — payloads sent as-is.
* ``anonymised``     — regex PII scrub (emails, phones, API keys, hex tokens).
* ``metadata_only``  — payloads suppressed; only spans and timings recorded.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Literal

from whitespace.config import Config

logger = logging.getLogger(__name__)

ConsentTier = Literal["full", "anonymised", "metadata_only"]

_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:sk|pk|lsv2|lsv1)[_-][A-Za-z0-9_-]{16,}\b"),
        "<api-key>",
    ),
    (
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "<email>",
    ),
    (
        re.compile(r"\+?\d[\d\s().-]{8,}\d"),
        "<phone>",
    ),
    (
        re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
        "<token>",
    ),
)


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        out = value
        for pattern, replacement in _PII_PATTERNS:
            out = pattern.sub(replacement, out)
        return out
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _anonymiser(payload: dict[str, Any]) -> dict[str, Any]:
    scrubbed = _scrub(payload)
    return scrubbed if isinstance(scrubbed, dict) else {"value": scrubbed}


def build_langsmith_client(config: Config) -> object | None:
    """Construct a LangSmith Client configured for the consent tier.

    Returns None when tracing is disabled or no API key is set.
    """
    if not config.langsmith_tracing:
        return None

    api_key = config.langsmith_api_key.strip()
    if not api_key:
        return None

    from langsmith import Client

    endpoint = config.langsmith_endpoint or "https://api.smith.langchain.com"
    tier = config.langsmith_consent_tier

    kwargs: dict[str, Any] = {"api_key": api_key, "api_url": endpoint}
    if tier == "anonymised":
        kwargs["anonymizer"] = _anonymiser
    elif tier == "metadata_only":
        kwargs["hide_inputs"] = True
        kwargs["hide_outputs"] = True

    try:
        return Client(**kwargs)
    except Exception:
        logger.warning(
            "Failed to construct LangSmith client for tier=%s; "
            "tracing will fall back to env-driven default",
            tier,
            exc_info=True,
        )
        return None


def configure_tracing_env(config: Config) -> None:
    """Set LangSmith environment variables so LangGraph traces automatically.

    Call once at startup. LangGraph and LangChain read these env vars
    to decide whether to send traces.
    """
    if not config.langsmith_tracing or not config.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "false"
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = config.langsmith_api_key
    os.environ["LANGSMITH_ENDPOINT"] = (
        config.langsmith_endpoint or "https://api.smith.langchain.com"
    )
    if config.langsmith_project:
        os.environ["LANGSMITH_PROJECT"] = config.langsmith_project

    logger.info(
        "LangSmith tracing enabled (tier=%s, project=%s)",
        config.langsmith_consent_tier,
        config.langsmith_project or "<default>",
    )
