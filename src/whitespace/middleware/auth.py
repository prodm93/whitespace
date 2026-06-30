import logging

from fastapi import HTTPException, Request

from whitespace.config import Config

logger = logging.getLogger(__name__)


class CurrentUser:
    """Identity + tier extracted from the auth layer."""

    def __init__(self, user_id: str, tier: str) -> None:
        self.user_id = user_id
        self.tier = tier


_jwks_client_cache: dict[str, object] = {}


async def get_current_user(request: Request) -> CurrentUser:
    """Validate auth and extract user identity + tier.

    In BYOK mode, returns a synthetic user with no tier restrictions.
    In SaaS mode, validates the Clerk JWT from the Authorization header.
    """
    config: Config = request.app.state.config
    if config.mode == "byok":
        return CurrentUser(user_id="byok", tier="unlimited")

    return await _validate_clerk_jwt(request, config)


async def _validate_clerk_jwt(request: Request, config: Config) -> CurrentUser:
    import asyncio

    import jwt
    from jwt import PyJWKClient

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth_header[7:]

    jwks_url = config.clerk_jwks_url
    if not jwks_url:
        raise HTTPException(status_code=500, detail="Clerk JWKS URL not configured")

    if jwks_url not in _jwks_client_cache:
        _jwks_client_cache[jwks_url] = PyJWKClient(jwks_url)

    jwks_client: PyJWKClient = _jwks_client_cache[jwks_url]  # type: ignore[assignment]

    try:
        signing_key = await asyncio.to_thread(jwks_client.get_signing_key_from_jwt, token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=config.clerk_issuer or None,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError as exc:
        logger.warning("Clerk JWT validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token") from None

    user_id = claims.get("sub", "")
    tier = claims.get("metadata", {}).get("tier", "free")

    if not user_id:
        raise HTTPException(status_code=401, detail="No subject in token")

    return CurrentUser(user_id=user_id, tier=tier)
