"""Lambda handler — fans out USPTO + web search queries, writes results to S3."""

import asyncio
import json
import logging
import os
import uuid

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", "")
AWS_REGION = os.environ.get("AWS_REGION", "sa-east-1")

_s3_client = None


def _get_s3() -> object:
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


def handler(event: dict, context: object) -> dict:
    """Receives search config, fans out queries, writes normalised results to S3."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Invalid JSON body"})

    domain_keywords = body.get("domain_keywords", [])
    cpc_classes = body.get("cpc_classes", [])

    if not domain_keywords:
        return _response(400, {"error": "domain_keywords required"})

    results = asyncio.get_event_loop().run_until_complete(
        _fan_out_search(domain_keywords, cpc_classes)
    )

    result_key = f"search-results/{uuid.uuid4()}.json"
    _get_s3().put_object(
        Bucket=RESULTS_BUCKET,
        Key=result_key,
        Body=json.dumps(results),
        ContentType="application/json",
    )

    return _response(
        200,
        {
            "result_key": result_key,
            "patent_count": len(results.get("patents", [])),
            "web_count": len(results.get("web_results", [])),
        },
    )


async def _fan_out_search(
    keywords: list[str],
    cpc_classes: list[str],
) -> dict:
    patent_task = _search_uspto(keywords, cpc_classes)
    web_task = _search_web(keywords)

    patents, web_results = await asyncio.gather(
        patent_task,
        web_task,
        return_exceptions=True,
    )

    if isinstance(patents, Exception):
        logger.error("USPTO search failed: %s", patents)
        patents = []
    if isinstance(web_results, Exception):
        logger.error("Web search failed: %s", web_results)
        web_results = []

    return {"patents": patents, "web_results": web_results}


async def _search_uspto(
    keywords: list[str],
    cpc_classes: list[str],
) -> list[dict]:
    import httpx

    query_terms = " OR ".join(f'"{kw}"' for kw in keywords)
    params: dict = {
        "q": json.dumps({"_text_any": {"patent_abstract": query_terms}}),
        "f": json.dumps(
            [
                "patent_number",
                "patent_title",
                "patent_abstract",
                "patent_date",
                "inventor_first_name",
                "inventor_last_name",
            ]
        ),
        "o": json.dumps({"per_page": 50}),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://api.patentsview.org/patents/query",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    patents = data.get("patents", []) or []
    return [
        {
            "source_type": "api",
            "patent_number": p.get("patent_number", ""),
            "title": p.get("patent_title", ""),
            "abstract": p.get("patent_abstract", ""),
            "date": p.get("patent_date", ""),
        }
        for p in patents
    ]


async def _search_web(keywords: list[str]) -> list[dict]:
    from duckduckgo_search import DDGS

    query = " ".join(keywords) + " patent limitations gaps unmet needs"
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None,
        lambda: list(DDGS().text(query, max_results=20)),
    )

    return [
        {
            "source_type": "web",
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in results
    ]


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
