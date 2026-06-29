import logging

from fastapi import Depends, Request

from whitespace.config import Config
from whitespace.middleware.auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

TIER_LIMITS: dict[str, dict[str, int]] = {
    "free": {"runs": 2, "files": 3, "upload_mb": 50},
    "standard": {"runs": 40, "files": 10, "upload_mb": 200},
    "pro": {"runs": -1, "files": 50, "upload_mb": 1024},
    "unlimited": {"runs": -1, "files": -1, "upload_mb": -1},
}

MONTHLY_RESET_TIERS = {"standard", "pro"}


async def check_usage(
    request: Request,
    user: CurrentUser = Depends(get_current_user),  # noqa: B008
) -> None:
    """Enforce tier-based usage limits.

    In BYOK mode this is a no-op. In SaaS mode, reads run counts
    from DynamoDB and returns 429 when the tier limit is exceeded.
    """
    config: Config = request.app.state.config
    if config.mode == "byok":
        return

    raise NotImplementedError("SaaS usage enforcement requires Phase 14a")


async def increment_run_count(config: Config, user_id: str) -> None:
    """Increment the run counter after a successful job enqueue."""
    if config.mode == "byok":
        return

    raise NotImplementedError("SaaS usage tracking requires Phase 14a")
