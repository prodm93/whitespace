"""Semantic Scholar API client for prior-art searches."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_SEARCH_FIELDS = "title,abstract,authors,year,citationCount"


class ScholarClient:
    """Queries the Semantic Scholar API (no API key required)."""

    async def search_papers(
        self,
        query: str,
        *,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for academic papers and return parsed results."""
        logger.info("Scholar search: query=%r max=%d", query, max_results)
        raw = await self._get(query, max_results=max_results)
        return self._parse_response(raw)

    async def _get(
        self,
        query: str,
        *,
        max_results: int,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "query": query,
            "limit": min(max_results, 100),
            "fields": _SEARCH_FIELDS,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{_BASE_URL}/paper/search",
                params=params,
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

    def _parse_response(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        papers_raw = raw.get("data") or []
        results: list[dict[str, Any]] = []
        for paper in papers_raw:
            authors = [
                author.get("name", "")
                for author in (paper.get("authors") or [])
                if author.get("name")
            ]
            results.append(
                {
                    "title": paper.get("title", ""),
                    "abstract": paper.get("abstract") or "",
                    "authors": authors,
                    "year": paper.get("year"),
                    "citation_count": paper.get("citationCount", 0),
                }
            )
        logger.info("Scholar search returned %d papers", len(results))
        return results
