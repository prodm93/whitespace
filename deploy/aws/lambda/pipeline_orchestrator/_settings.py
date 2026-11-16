"""The configuration of the SaaS pipeline function, with its secrets read from Secrets Manager."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from whitespace.config import Config
from whitespace.tools.retry import transient_retry

logger = logging.getLogger(__name__)

REQUIRED = ("neo4j_uri", "neo4j_username", "neo4j_password")
OPTIONAL = ("exa_api_key", "langsmith_api_key")
MAX_AGE_SECONDS = 300
SECRET_ENV = "PIPELINE_SECRET_ARN"
USER_MESSAGE = "The analysis could not start because of a configuration problem on our side. Please try again later."  # noqa: E501


class SecretsError(RuntimeError):
    """The secrets could not be read or checked; the text is always ``USER_MESSAGE``."""

    def __init__(self) -> None:
        super().__init__(USER_MESSAGE)


class _Unreachable(Exception):
    """A read that failed in a way worth another attempt."""


_provider: Any = None
_last_good: Config | None = None


def _new_client() -> Any:
    import boto3
    from botocore.config import Config as BotoConfig

    return boto3.client(
        "secretsmanager",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        config=BotoConfig(retries={"total_max_attempts": 1}),
    )


def _get_provider() -> Any:
    global _provider
    if _provider is None:
        from aws_lambda_powertools.utilities.parameters import SecretsProvider

        _provider = SecretsProvider(boto3_client=_new_client())
    return _provider


def _read(arn: str) -> Any:
    """Read and parse the secret once; a fault worth another attempt raises ``_Unreachable``.

    The raw value never reaches an error or a log line: a value that is not JSON is
    reported outside the ``except`` block, so the parse error that holds the text is not
    chained to the raised error.
    """
    from aws_lambda_powertools.utilities.parameters.exceptions import (
        GetParameterError,
        TransformParameterError,
    )
    from botocore.exceptions import ClientError

    not_json = False
    try:
        return _get_provider().get(arn, max_age=MAX_AGE_SECONDS, transform="json")
    except TransformParameterError:
        not_json = True
    except GetParameterError as error:
        cause = error.__context__
        if _is_transient(cause):
            raise _Unreachable() from cause
        if isinstance(cause, ClientError):
            logger.error("The pipeline secret could not be read: %s", _error_code(cause))
            raise SecretsError() from cause
        failure = type(cause).__name__
    if not_json:
        logger.error("The pipeline secret is not valid JSON")
    else:
        logger.error("The pipeline secret could not be read: %s", failure)
    raise SecretsError()


def _is_transient(error: BaseException | None) -> bool:
    from botocore.exceptions import (
        ClientError,
        ConnectTimeoutError,
        EndpointConnectionError,
        ReadTimeoutError,
    )

    if isinstance(error, EndpointConnectionError | ConnectTimeoutError | ReadTimeoutError):
        return True
    return isinstance(error, ClientError) and _error_code(error) == "InternalServiceError"


def _error_code(error: Any) -> str:
    return str(error.response.get("Error", {}).get("Code", "unknown"))


def _checked_values(value: Any) -> dict[str, str]:
    """Return the known keys of the secret, or raise when a required one has no text value."""
    if not isinstance(value, dict):
        logger.error("The pipeline secret is not a JSON object")
        raise SecretsError()
    missing = [name for name in REQUIRED if not _is_text(value.get(name))]
    if missing:
        logger.error("The pipeline secret has no value for: %s", ", ".join(missing))
        raise SecretsError()
    values = {name: value[name] for name in REQUIRED}
    unset = [name for name in OPTIONAL if not _is_text(value.get(name))]
    for name in OPTIONAL:
        values[name] = "" if name in unset else value[name]
    if unset:
        logger.info("The pipeline secret has no value for the optional keys: %s", ", ".join(unset))
    unknown = sorted(str(name) for name in value if name not in (*REQUIRED, *OPTIONAL))
    if unknown:
        logger.warning("The pipeline secret has keys that are not used: %s", ", ".join(unknown))
    return values


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


async def load_config() -> Config:
    """Return the function's ``Config`` with the values of the pipeline secret filled in.

    The secret is read at most once every ``MAX_AGE_SECONDS``. A read that AWS does not
    answer is tried three times; when it still fails, the last good ``Config`` is returned
    if one exists. Every other failure raises ``SecretsError``, whose text is
    ``USER_MESSAGE``. No secret value is ever logged or put in an error.
    """
    global _last_good
    arn = os.environ.get(SECRET_ENV, "")
    if not arn:
        logger.error("PIPELINE_SECRET_ARN is not set")
        raise SecretsError()

    async def read_once() -> Any:
        return await asyncio.to_thread(_read, arn)

    policy = transient_retry(attempts=3, first_wait=0.5, max_wait=2.0, retry_on=(_Unreachable,))
    try:
        value = await policy(read_once)
    except _Unreachable as unreachable:
        if _last_good is not None:
            logger.warning("The pipeline secret could not be read again; the last values are used")
            return _last_good
        logger.error("The pipeline secret could not be read: Secrets Manager did not answer")
        raise SecretsError() from unreachable.__cause__
    config = Config(**_checked_values(value))
    _last_good = config
    return config
