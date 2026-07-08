"""Executes research queries across USPTO, Semantic Scholar, and the web.

Pure I/O: takes queries, returns dated RawFinding objects. Query
formulation and judgment about the results belong to the calling agents.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from whitespace.schemas.research import RawFinding
from whitespace.tools.search.scholar_client import ScholarClient
from whitespace.tools.search.uspto_client import UsptpClient
from whitespace.tools.search.web_search import WebSearch

logger = logging.getLogger(__name__)

_PER_QUERY_RESULTS = 8


class ResearchExecutor:
    """Runs each query against all three surfaces in parallel."""

    def __init__(
        self,
        uspto: UsptpClient,
        scholar: ScholarClient,
        web: WebSearch,
    ) -> None:
        self._uspto = uspto
        self._scholar = scholar
        self._web = web

    async def run(
        self,
        queries: list[str],
        *,
        per_query: int = _PER_QUERY_RESULTS,
    ) -> list[RawFinding]:
        """Execute every query on every surface; failures degrade to empty."""
        tasks = [self._run_one(query, per_query) for query in queries]
        batches = await asyncio.gather(*tasks)
        findings = [f for batch in batches for f in batch]
        logger.info(
            "ResearchExecutor: %d queries -> %d findings",
            len(queries),
            len(findings),
        )
        return findings

    async def _run_one(self, query: str, per_query: int) -> list[RawFinding]:
        patents, papers, pages = await asyncio.gather(
            _safe(self._uspto.search_patents(query, max_results=per_query), "uspto", query),
            _safe(self._scholar.search_papers(query, max_results=per_query), "scholar", query),
            _safe(self._web.search(query, max_results=per_query), "web", query),
        )
        findings: list[RawFinding] = []
        for p in patents:
            findings.append(
                RawFinding(
                    title=p.get("title", ""),
                    content=p.get("abstract", ""),
                    source_type="patent",
                    source_url=None,
                    source_name=p.get("patent_number", "") or p.get("title", ""),
                    query=query,
                    published=p.get("patent_date") or None,
                )
            )
        for p in papers:
            findings.append(
                RawFinding(
                    title=p.get("title", ""),
                    content=p.get("abstract", ""),
                    source_type="paper",
                    source_url=None,
                    source_name=p.get("title", ""),
                    query=query,
                    published=str(p["year"]) if p.get("year") else None,
                )
            )
        for page in pages:
            url = page.get("url", "")
            findings.append(
                RawFinding(
                    title=page.get("title", ""),
                    content=page.get("snippet", ""),
                    source_type="web",
                    source_url=url or None,
                    source_name=urlparse(url).netloc if url else page.get("title", ""),
                    query=query,
                )
            )
        return findings


async def _safe(
    coro: Any,
    surface: str,
    query: str,
) -> list[dict[str, Any]]:
    try:
        result: list[dict[str, Any]] = await coro
        return result
    except Exception:
        logger.warning("ResearchExecutor: %s search failed for %r", surface, query)
        return []
