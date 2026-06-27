"""Tri-modal input normaliser — deterministic mapping, no LLM calls."""

from __future__ import annotations

import logging
from typing import Any

from whitespace.schemas.patent import NormalisedDocument

logger = logging.getLogger(__name__)

_USPTO_URL_TEMPLATE = "https://patents.google.com/patent/US{patent_number}"


class Normaliser:
    """Transforms raw search results into a unified document schema."""

    def from_uspto(self, raw: dict[str, Any]) -> NormalisedDocument:
        """Map a parsed USPTO dict to a NormalisedDocument."""
        patent_number = raw.get("patent_number", "")
        title = raw.get("title", "")
        abstract = raw.get("abstract", "")
        claims = raw.get("claims", "")
        description = raw.get("description", "")

        parts = [p for p in (abstract, claims, description) if p]
        content = "\n\n".join(parts) if parts else title

        metadata: dict[str, Any] = {}
        if raw.get("inventors"):
            metadata["inventors"] = raw["inventors"]
        if raw.get("cpc_codes"):
            metadata["cpc_codes"] = raw["cpc_codes"]
        if raw.get("citations"):
            metadata["citations"] = raw["citations"]

        source_url = (
            _USPTO_URL_TEMPLATE.format(patent_number=patent_number) if patent_number else None
        )

        return NormalisedDocument(
            title=title,
            content=content,
            source_type="api",
            source_url=source_url,
            source_name=patent_number or title,
            metadata=metadata,
        )

    def from_web(self, url: str, content: str) -> NormalisedDocument:
        """Normalise web-crawled content."""
        title = _extract_title(content, fallback=url)
        return NormalisedDocument(
            title=title,
            content=content,
            source_type="web",
            source_url=url,
            source_name=url,
            metadata={},
        )

    def from_upload(self, filename: str, content: str) -> NormalisedDocument:
        """Normalise a user-uploaded document."""
        title = _extract_title(content, fallback=filename)
        return NormalisedDocument(
            title=title,
            content=content,
            source_type="pdf",
            source_url=None,
            source_name=filename,
            metadata={},
        )


def _extract_title(content: str, *, fallback: str) -> str:
    first_line = content.strip().split("\n", maxsplit=1)[0].strip()
    if first_line and len(first_line) <= 200:
        return first_line
    return fallback
