"""Web search with Exa (semantic) and DuckDuckGo (free fallback)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class WebSearch:
    """Tries Exa first; falls back to DuckDuckGo if key missing or error."""

    def __init__(self, *, exa_api_key: str = "") -> None:
        self._exa_api_key = exa_api_key

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> list[dict[str, str]]:
        """Return a list of ``{url, title, snippet}`` dicts."""
        logger.info("WebSearch: query=%r max=%d", query, max_results)
        if self._exa_api_key:
            try:
                return await self._search_exa(query, max_results=max_results)
            except Exception:
                logger.warning("Exa search failed, falling back to DuckDuckGo")
        return await self._search_ddg(query, max_results=max_results)

    async def _search_exa(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[dict[str, str]]:
        from exa_py import Exa

        exa = Exa(api_key=self._exa_api_key)
        response = await asyncio.to_thread(
            exa.search_and_contents,
            query,
            num_results=max_results,
            use_autoprompt=True,
            text=True,
        )
        results: list[dict[str, str]] = []
        for item in response.results:
            results.append(
                {
                    "url": getattr(item, "url", ""),
                    "title": getattr(item, "title", ""),
                    "snippet": (getattr(item, "text", "") or "")[:500],
                }
            )
        logger.info("Exa returned %d results", len(results))
        return results

    async def _search_ddg(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[dict[str, str]]:
        return await asyncio.to_thread(self._search_ddg_sync, query, max_results=max_results)

    def _search_ddg_sync(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[dict[str, str]]:
        from duckduckgo_search import DDGS

        results: list[dict[str, str]] = []
        try:
            ddg = DDGS()
            raw: list[dict[str, Any]] = ddg.text(query, max_results=max_results)
            for item in raw:
                results.append(
                    {
                        "url": item.get("href", ""),
                        "title": item.get("title", ""),
                        "snippet": item.get("body", ""),
                    }
                )
        except Exception:
            logger.exception("DuckDuckGo search failed for query=%r", query)
        logger.info("DuckDuckGo returned %d results", len(results))
        return results
