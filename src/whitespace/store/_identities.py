"""What makes a stored finding or rejection the same as another, and a digest of it for keys."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from whitespace.schemas.research import RawFinding


def finding_identity(finding: RawFinding) -> tuple[str, str, str]:
    """Source type, link (or source name when there is no link) and query.

    The retrieval time and the text are not part of it, so a repeated search
    that returns the same result matches the stored finding.
    """
    return (finding.source_type, finding.source_url or finding.source_name, finding.query)


def discard_identity(entry: dict[str, str]) -> tuple[str, str, str]:
    """Title, description and reason of a rejection."""
    return (entry.get("title", ""), entry.get("description", ""), entry.get("reason", ""))


def identity_digest(parts: Sequence[str]) -> str:
    """The SHA-256 digest, in hexadecimal, of the parts written as a JSON array.

    Each part is quoted and its quotes, backslashes and control characters are escaped,
    so two different lists of parts never give the same text, whatever characters they
    hold. Every argument of the call is fixed: changing one changes every stored key.
    """
    text = json.dumps(list(parts), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
