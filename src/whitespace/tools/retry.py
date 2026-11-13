"""The retry policy for transient errors, built on tenacity."""

from __future__ import annotations

import logging

from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def transient_retry(
    *,
    attempts: int,
    first_wait: float,
    max_wait: float,
    retry_on: tuple[type[BaseException], ...],
) -> AsyncRetrying:
    """Return a policy that tries a call ``attempts`` times in total.

    Only the ``retry_on`` types are retried; any other error comes out at once. Waits
    start at ``first_wait`` seconds and double up to ``max_wait``. When the attempts run
    out, the last error itself is raised. Use as ``await transient_retry(...)(fn, *args)``.
    """
    return AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=first_wait, max=max_wait),
        retry=retry_if_exception_type(retry_on),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
