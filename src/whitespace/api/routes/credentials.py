import asyncio
import logging

from fastapi import APIRouter
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable
from openai import AsyncOpenAI

from whitespace.api.models import (
    CredentialValidateRequest,
    CredentialValidateResponse,
)
from whitespace.models.providers import OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/credentials/validate",
    response_model=CredentialValidateResponse,
)
async def validate_credentials(
    request: CredentialValidateRequest,
) -> CredentialValidateResponse:
    """Validate BYOK credentials by testing both connections in parallel."""
    logger.info("Credential validation requested")
    creds = request.credentials
    openrouter_task = _check_openrouter(creds.openrouter_api_key)
    neo4j_task = _check_neo4j(
        creds.neo4j_uri,
        creds.neo4j_username,
        creds.neo4j_password,
    )
    (or_ok, or_err), (n4j_ok, n4j_err) = await asyncio.gather(
        openrouter_task,
        neo4j_task,
    )
    return CredentialValidateResponse(
        openrouter_ok=or_ok,
        neo4j_ok=n4j_ok,
        openrouter_error=or_err,
        neo4j_error=n4j_err,
    )


async def _check_openrouter(api_key: str) -> tuple[bool, str | None]:
    try:
        client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
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
    driver = None
    try:
        driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
        await driver.verify_connectivity()
        return True, None
    except ServiceUnavailable as exc:
        logger.warning("Neo4j validation failed: %s", exc)
        return False, str(exc)
    except Exception as exc:
        logger.warning("Neo4j validation failed: %s", exc)
        return False, str(exc)
    finally:
        if driver is not None:
            await driver.close()
