"""API Gateway Lambda authoriser — validates Clerk JWTs."""

import logging
import os

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CLERK_JWKS_URL = os.environ.get("CLERK_JWKS_URL", "")
CLERK_ISSUER = os.environ.get("CLERK_ISSUER", "")

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        if not CLERK_JWKS_URL:
            raise ValueError("CLERK_JWKS_URL not configured")
        _jwks_client = PyJWKClient(CLERK_JWKS_URL)
    return _jwks_client


def handler(event: dict, context: object) -> dict:
    """API Gateway HTTP API payload format 2.0 authoriser.

    Returns simple response: isAuthorized bool + context with user_id and tier.
    """
    headers = event.get("headers", {})
    auth_header = headers.get("authorization", "")

    if not auth_header.startswith("Bearer "):
        logger.info("Missing Bearer token")
        return {"isAuthorized": False}

    token = auth_header[7:]

    try:
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        decode_opts: dict = {"algorithms": ["RS256"]}
        if CLERK_ISSUER:
            decode_opts["issuer"] = CLERK_ISSUER

        claims = jwt.decode(token, signing_key.key, **decode_opts)
    except jwt.ExpiredSignatureError:
        logger.info("Token expired")
        return {"isAuthorized": False}
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT validation failed: %s", exc)
        return {"isAuthorized": False}
    except Exception as exc:
        logger.error("Authoriser error: %s", exc)
        return {"isAuthorized": False}

    user_id = claims.get("sub", "")
    if not user_id:
        logger.info("No subject in token")
        return {"isAuthorized": False}

    tier = claims.get("metadata", {}).get("tier", "free")

    return {
        "isAuthorized": True,
        "context": {
            "user_id": user_id,
            "tier": tier,
        },
    }
