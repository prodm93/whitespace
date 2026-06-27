"""Tests for WebSearch fallback logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whitespace.tools.search.web_search import WebSearch

_DDG_RAW = [
    {"href": "https://a.com", "title": "Result A", "body": "Snippet A"},
    {"href": "https://b.com", "title": "Result B", "body": "Snippet B"},
]


class TestNoExaKey:
    """When no Exa key is provided, DuckDuckGo is used directly."""

    @pytest.mark.asyncio
    async def test_ddg_used_when_exa_key_empty(self) -> None:
        ws = WebSearch(exa_api_key="")
        with (
            patch.object(ws, "_search_exa", new_callable=AsyncMock) as mock_exa,
            patch.object(ws, "_search_ddg", new_callable=AsyncMock) as mock_ddg,
        ):
            mock_ddg.return_value = [
                {"url": "https://a.com", "title": "A", "snippet": "S"},
            ]
            results = await ws.search("test query", max_results=5)

        mock_exa.assert_not_called()
        mock_ddg.assert_awaited_once_with("test query", max_results=5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_ddg_sync_parses_raw_format(self) -> None:
        ws = WebSearch(exa_api_key="")
        ddgs_instance = MagicMock()
        ddgs_instance.text.return_value = _DDG_RAW

        with patch("duckduckgo_search.DDGS", return_value=ddgs_instance):
            results = ws._search_ddg_sync("battery patents", max_results=2)

        assert len(results) == 2
        assert results[0] == {
            "url": "https://a.com",
            "title": "Result A",
            "snippet": "Snippet A",
        }
        assert results[1]["url"] == "https://b.com"


class TestExaFallback:
    """When Exa key is present but Exa fails, fall back to DuckDuckGo."""

    @pytest.mark.asyncio
    async def test_falls_back_to_ddg_on_exa_error(self) -> None:
        ws = WebSearch(exa_api_key="sk-test-key")
        ddg_results = [{"url": "https://c.com", "title": "C", "snippet": "SC"}]

        with (
            patch.object(
                ws, "_search_exa", new_callable=AsyncMock, side_effect=RuntimeError("API down")
            ),
            patch.object(
                ws, "_search_ddg", new_callable=AsyncMock, return_value=ddg_results
            ) as mock_ddg,
        ):
            results = await ws.search("test", max_results=3)

        mock_ddg.assert_awaited_once_with("test", max_results=3)
        assert results == ddg_results

    @pytest.mark.asyncio
    async def test_exa_used_when_key_present_and_succeeds(self) -> None:
        ws = WebSearch(exa_api_key="sk-test-key")
        exa_results = [{"url": "https://exa.com", "title": "E", "snippet": "SE"}]

        with (
            patch.object(
                ws, "_search_exa", new_callable=AsyncMock, return_value=exa_results
            ) as mock_exa,
            patch.object(ws, "_search_ddg", new_callable=AsyncMock) as mock_ddg,
        ):
            results = await ws.search("test", max_results=5)

        mock_exa.assert_awaited_once_with("test", max_results=5)
        mock_ddg.assert_not_called()
        assert results == exa_results
