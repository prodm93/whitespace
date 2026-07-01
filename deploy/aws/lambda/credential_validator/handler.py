"""Lambda handler — validates OpenRouter API key and Neo4j connectivity."""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    """API Gateway HTTP API payload format 2.0 handler."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Invalid JSON body"})

    creds = body.get("credentials", {})
    openrouter_key = creds.get("openrouter_api_key", "")
    neo4j_uri = creds.get("neo4j_uri", "")
    neo4j_username = creds.get("neo4j_username", "")
    neo4j_password = creds.get("neo4j_password", "")

    if not openrouter_key or not neo4j_uri:
        return _response(400, {"error": "Missing required credentials"})

    or_ok, or_err, n4j_ok, n4j_err = asyncio.get_event_loop().run_until_complete(
        _validate(openrouter_key, neo4j_uri, neo4j_username, neo4j_password)
    )

    return _response(
        200,
        {
            "openrouter_ok": or_ok,
            "neo4j_ok": n4j_ok,
            "openrouter_error": or_err,
            "neo4j_error": n4j_err,
        },
    )


async def _validate(
    openrouter_key: str,
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
) -> tuple[bool, str | None, bool, str | None]:
    (or_ok, or_err), (n4j_ok, n4j_err) = await asyncio.gather(
        _check_openrouter(openrouter_key),
        _check_neo4j(neo4j_uri, neo4j_username, neo4j_password),
    )
    return or_ok, or_err, n4j_ok, n4j_err


async def _check_openrouter(api_key: str) -> tuple[bool, str | None]:
    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        await client.models.list()
        return True, None
    except Exception as exc:
        logger.warning("OpenRouter validation failed: %s", exc)
        return False, str(exc)


async def _check_neo4j(
    uri: str,
    username: str,
    password: str,
) -> tuple[bool, str | None]:
    from neo4j import AsyncGraphDatabase

    driver = None
    try:
        driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
        await driver.verify_connectivity()
        return True, None
    except Exception as exc:
        logger.warning("Neo4j validation failed: %s", exc)
        return False, str(exc)
    finally:
        if driver is not None:
            await driver.close()


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
