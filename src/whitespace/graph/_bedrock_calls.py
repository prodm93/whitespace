"""One Bedrock call from async code, with the errors worth another attempt marked.

boto3 and botocore are imported inside the functions, so this module is safe to import
in BYOK mode.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from whitespace.tools.retry import transient_retry

TRANSIENT_CODES = frozenset(
    {
        "ThrottlingException",
        "ModelTimeoutException",
        "ServiceUnavailableException",
        "InternalServerException",
        "ModelNotReadyException",
        "DependencyFailedException",
        "BadGatewayException",
    }
)


def _client(service: str, region: str) -> Any:
    import boto3
    from botocore.config import Config as BotoConfig

    return boto3.client(
        service, region_name=region, config=BotoConfig(retries={"total_max_attempts": 1})
    )


def runtime_client(region: str) -> Any:
    """A ``bedrock-runtime`` client that makes one attempt for each call."""
    return _client("bedrock-runtime", region)


def agent_runtime_client(region: str) -> Any:
    """A ``bedrock-agent-runtime`` client that makes one attempt for each call."""
    return _client("bedrock-agent-runtime", region)


async def call(operation: Callable[..., Any], **kwargs: Any) -> Any:
    """Run the blocking ``operation`` in a thread and return its answer.

    Throttling, timeouts, an unavailable service, a failed connection and a body that
    breaks off while it is read are raised as the built-in ``ConnectionError``, chained
    from the original error. Every other error comes out unchanged.
    """
    from botocore.exceptions import (
        ClientError,
        IncompleteReadError,
        ReadTimeoutError,
        ResponseStreamingError,
    )
    from botocore.exceptions import ConnectionError as BotoConnectionError

    try:
        return await asyncio.to_thread(operation, **kwargs)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in TRANSIENT_CODES:
            raise ConnectionError(str(error)) from error
        raise
    except (
        BotoConnectionError,
        ReadTimeoutError,
        ResponseStreamingError,
        IncompleteReadError,
    ) as error:
        raise ConnectionError(str(error)) from error


def invoke_model_json(client: Any, **kwargs: Any) -> Any:
    """Call ``invoke_model``, then read and parse the streamed body, closing it on every exit.

    It is blocking; run it through ``call`` so that the read happens in the worker thread
    and its errors are treated like errors of the call.
    """
    body = client.invoke_model(**kwargs)["body"]
    try:
        return json.loads(body.read())
    finally:
        body.close()


async def call_with_retry(operation: Callable[..., Any], **kwargs: Any) -> Any:
    """``call``, tried three times in all when the error is a ``ConnectionError``."""
    policy = transient_retry(attempts=3, first_wait=1.0, max_wait=8.0, retry_on=(ConnectionError,))
    return await policy(call, operation, **kwargs)
