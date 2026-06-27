"""Web content extraction — Firecrawl with httpx fallback."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

logger = logging.getLogger(__name__)


class WebCrawler:
    """Extracts clean text from a URL.

    Uses Firecrawl when an API key is provided (returns markdown).
    Falls back to a basic httpx fetch with HTML tag stripping.
    """

    def __init__(self, *, firecrawl_api_key: str = "") -> None:
        self._firecrawl_api_key = firecrawl_api_key

    async def extract(self, url: str) -> str:
        """Fetch ``url`` and return clean text content."""
        logger.info("WebCrawler: extracting %s", url)
        if self._firecrawl_api_key:
            try:
                return await self._extract_firecrawl(url)
            except Exception:
                logger.warning("Firecrawl failed for %s, falling back to httpx", url)
        return await self._extract_httpx(url)

    async def _extract_firecrawl(self, url: str) -> str:
        from firecrawl import FirecrawlApp

        app = FirecrawlApp(api_key=self._firecrawl_api_key)
        response = await asyncio.to_thread(
            app.scrape_url,
            url,
            formats=["markdown"],
            only_main_content=True,
        )
        markdown = getattr(response, "markdown", None) or ""
        if not markdown and isinstance(response, dict):
            markdown = response.get("markdown", "")
        logger.info("Firecrawl extracted %d chars from %s", len(markdown), url)
        return markdown

    async def _extract_httpx(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            text = _strip_html(response.text)
        logger.info("httpx extracted %d chars from %s", len(text), url)
        return text


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\n{3,}")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = _WHITESPACE_RE.sub("\n\n", text)
    return text.strip()
