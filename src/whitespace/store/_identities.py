"""What makes a stored finding or rejection the same as another."""

from __future__ import annotations

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
