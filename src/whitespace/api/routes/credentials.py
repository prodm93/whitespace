"""Credential routes.

* ``POST /api/credentials/parse`` — accepts a Neo4j Aura ``.txt`` upload and
  returns the parsed key/value pairs as JSON.
* ``POST /api/credentials`` — accepts the full credential set as JSON,
  persists to ``.env`` (0600 permissions), reloads into ``os.environ``,
  validates connectivity, and resets cached state.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from whitespace.api.state import app_state
from whitespace.models.providers import OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_CREDS_FILE_BYTES = 64 * 1024
ENV_FILE = Path(os.environ.get("CREDS_ENV_FILE", ".env"))
CRED_MAX = 512

REQUIRED_AURA_FILE_KEYS: tuple[str, ...] = (
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
)


class CredentialsPayload(BaseModel):
    openrouter_api_key: str = Field("", max_length=CRED_MAX)
    neo4j_uri: str = Field("", max_length=CRED_MAX)
    neo4j_username: str = Field("", max_length=CRED_MAX)
    neo4j_password: str = Field("", max_length=CRED_MAX)
    neo4j_database: str = Field("", max_length=CRED_MAX)
    aura_instanceid: str = Field("", max_length=CRED_MAX)
    aura_instancename: str = Field("", max_length=CRED_MAX)
    exa_api_key: str = Field("", max_length=CRED_MAX)
    firecrawl_api_key: str = Field("", max_length=CRED_MAX)


class CredentialsResponse(BaseModel):
    status: str
    openrouter_ok: bool
    neo4j_ok: bool
    openrouter_error: str | None = None
    neo4j_error: str | None = None


@router.post("/credentials", response_model=CredentialsResponse)
async def set_credentials(payload: CredentialsPayload) -> CredentialsResponse:
    if not payload.openrouter_api_key.strip():
        raise HTTPException(status_code=400, detail="openrouter_api_key is required")

    uri = payload.neo4j_uri.strip()
    if (
        uri == ""
        and payload.aura_instanceid.strip() != ""
        and payload.aura_instancename.strip() != ""
    ):
        uri = f"neo4j+s://{payload.aura_instanceid.strip()}.databases.neo4j.io"
    if uri == "":
        raise HTTPException(
            status_code=400,
            detail="neo4j_uri is required (or supply both AURA instance ID and name)",
        )

    pairs: dict[str, str] = {
        "OPENROUTER_API_KEY": payload.openrouter_api_key.strip(),
        "NEO4J_URI": uri,
        "NEO4J_USERNAME": payload.neo4j_username.strip(),
        "NEO4J_PASSWORD": payload.neo4j_password,
        "NEO4J_DATABASE": payload.neo4j_database.strip() or "neo4j",
        "AURA_INSTANCEID": payload.aura_instanceid.strip(),
        "AURA_INSTANCENAME": payload.aura_instancename.strip(),
        "EXA_API_KEY": payload.exa_api_key.strip(),
        "FIRECRAWL_API_KEY": payload.firecrawl_api_key.strip(),
    }

    _persist_env(pairs)

    for key, value in pairs.items():
        os.environ[key] = value

    await app_state.reset()
    logger.info("Credentials persisted to %s; state cleared", ENV_FILE)

    (or_ok, or_err), (n4j_ok, n4j_err) = await asyncio.gather(
        _check_openrouter(payload.openrouter_api_key.strip()),
        _check_neo4j(uri, payload.neo4j_username.strip(), payload.neo4j_password),
    )

    return CredentialsResponse(
        status="ok",
        openrouter_ok=or_ok,
        neo4j_ok=n4j_ok,
        openrouter_error=or_err,
        neo4j_error=n4j_err,
    )


@router.post("/credentials/parse")
async def parse_credentials(file: UploadFile = File(...)) -> dict[str, str]:
    raw = await file.read(MAX_CREDS_FILE_BYTES + 1)
    await file.close()
    if len(raw) > MAX_CREDS_FILE_BYTES:
        raise HTTPException(status_code=400, detail="Credentials file too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Credentials file must be UTF-8 text") from exc

    entries = _parse_dotenv_lines(text)
    missing = [k for k in REQUIRED_AURA_FILE_KEYS if k not in entries or entries[k] == ""]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Credentials file missing required keys: {', '.join(missing)}",
        )

    return {
        "neo4j_uri": entries["NEO4J_URI"],
        "neo4j_username": entries["NEO4J_USERNAME"],
        "neo4j_password": entries["NEO4J_PASSWORD"],
        "neo4j_database": entries["NEO4J_DATABASE"],
        "aura_instanceid": entries.get("AURA_INSTANCEID", ""),
        "aura_instancename": entries.get("AURA_INSTANCENAME", ""),
    }


def _persist_env(pairs: dict[str, str]) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.touch(exist_ok=True)
    os.chmod(ENV_FILE, 0o600)

    existing = _parse_dotenv_lines(ENV_FILE.read_text()) if ENV_FILE.exists() else {}
    existing.update(pairs)

    lines = [f"{k}={v}" for k, v in existing.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n")
    os.chmod(ENV_FILE, 0o600)


def _parse_dotenv_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "" or line.startswith("#"):
            continue
        eq = line.find("=")
        if eq == -1:
            continue
        key = line[:eq].strip().upper()
        value = line[eq + 1 :].strip()
        if key == "":
            continue
        out[key] = value
    return out


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
