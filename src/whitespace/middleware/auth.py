import logging

from fastapi import Request

from whitespace.config import Config

logger = logging.getLogger(__name__)


class CurrentUser:
    """Identity + tier extracted from the auth layer."""

    def __init__(self, user_id: str, tier: str) -> None:
        self.user_id = user_id
        self.tier = tier


async def get_current_user(request: Request) -> CurrentUser:
    """Validate auth and extract user identity + tier.

    In BYOK mode, returns a synthetic user with no tier restrictions.
    In SaaS mode, validates the Clerk JWT from the Authorization header.
    """
    config: Config = request.app.state.config
    if config.mode == "byok":
        return CurrentUser(user_id="byok", tier="unlimited")

    raise NotImplementedError("SaaS auth requires Phase 14a")
