import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_async(
    fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    transient_exceptions: tuple[type[Exception], ...] = (
        TimeoutError,
        ConnectionError,
    ),
    **kwargs: Any,
) -> T:
    """Call *fn* with exponential backoff on transient errors.

    Non-transient exceptions propagate immediately.
    """
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await fn(*args, **kwargs)
        except transient_exceptions as exc:
            last_error = exc
            if attempt == retries:
                break
            delay = min(base_delay * (2**attempt), max_delay)
            logger.warning(
                "retry_async: attempt %d/%d failed (%s), retrying in %.1fs",
                attempt + 1,
                retries + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
        except Exception:
            raise
    raise RuntimeError(f"All {retries + 1} attempts failed") from last_error
