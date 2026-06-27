"""I/O tool for querying the USPTO PatentsView API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.patentsview.org/patents/query"

_DEFAULT_FIELDS = [
    "patent_number",
    "patent_title",
    "patent_abstract",
    "patent_date",
    "patent_num_claims",
]

_INVENTOR_FIELDS = [
    "inventor_first_name",
    "inventor_last_name",
]

_CPC_FIELDS = [
    "cpc_group_id",
    "cpc_group_title",
]


class UsptpClient:
    """Queries the USPTO PatentsView API and parses responses."""

    async def search_patents(
        self,
        query: str,
        *,
        cpc_class: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Search patents and return parsed results."""
        logger.info("USPTO search: query=%r cpc=%s max=%d", query, cpc_class, max_results)
        body = self._build_query(query, cpc_class=cpc_class, max_results=max_results)
        raw = await self._post(body)
        return self._parse_response(raw)

    def _build_query(
        self,
        query: str,
        *,
        cpc_class: str | None,
        max_results: int,
    ) -> dict[str, Any]:
        criteria: dict[str, Any] = {"_text_any": {"patent_abstract": query}}
        if cpc_class:
            criteria = {
                "_and": [
                    criteria,
                    {"cpc_group_id": cpc_class},
                ],
            }
        return {
            "q": criteria,
            "f": _DEFAULT_FIELDS + _INVENTOR_FIELDS + _CPC_FIELDS,
            "o": {
                "per_page": min(max_results, 100),
                "page": 1,
            },
        }

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _BASE_URL,
                json=body,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    def _parse_response(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        patents_raw = raw.get("patents") or []
        results: list[dict[str, Any]] = []
        for pat in patents_raw:
            inventors = [
                f"{inv.get('inventor_first_name', '')} {inv.get('inventor_last_name', '')}".strip()
                for inv in (pat.get("inventors") or [])
            ]
            cpc_codes = [
                cpc.get("cpc_group_id", "")
                for cpc in (pat.get("cpcs") or [])
                if cpc.get("cpc_group_id")
            ]
            results.append(
                {
                    "patent_number": pat.get("patent_number", ""),
                    "title": pat.get("patent_title", ""),
                    "abstract": pat.get("patent_abstract", ""),
                    "claims": "",
                    "description": "",
                    "inventors": inventors,
                    "citations": [],
                    "cpc_codes": cpc_codes,
                }
            )
        logger.info("USPTO search returned %d patents", len(results))
        return results
