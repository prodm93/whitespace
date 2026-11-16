"""A stand-in Secrets Manager client and the values the loader tests share."""

from __future__ import annotations

import importlib
from typing import Any

import _saas_helpers  # noqa: F401  (puts the pipeline function's folder on sys.path)
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

settings = importlib.import_module("_settings")

ARN = "arn:aws:secretsmanager:us-east-1:111122223333:secret:whitespace-dev-pipeline-AbCdEf"
SECRET = {
    "neo4j_uri": "neo4j+s://uri-QWXZ.databases.neo4j.io",
    "neo4j_username": "user-QWXZ",
    "neo4j_password": "password-QWXZ",
    "exa_api_key": "exa-QWXZ",
    "langsmith_api_key": "langsmith-QWXZ",
}


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "refused"}}, "GetSecretValue")


def unreachable() -> EndpointConnectionError:
    return EndpointConnectionError(endpoint_url="https://secretsmanager.us-east-1.amazonaws.com")


class StandInClient:
    """Answers ``get_secret_value`` from a queue of answers; each is a text or an error.

    Answers are given in turn and the last one repeats.
    """

    def __init__(self, *answers: str | BaseException) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def get_secret_value(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        return {
            "Name": "whitespace-dev-pipeline",
            "SecretString": answer,
            "VersionStages": ["AWSCURRENT"],
        }


def reset_loader(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Give the loader fresh module state and the secret's ARN; return a client installer."""
    monkeypatch.setenv("PIPELINE_SECRET_ARN", ARN)
    monkeypatch.setattr(settings, "_provider", None)
    monkeypatch.setattr(settings, "_last_good", None)

    def install(client: StandInClient) -> StandInClient:
        monkeypatch.setattr(settings, "_new_client", lambda: client)
        return client

    return install


def messages(caplog: pytest.LogCaptureFixture, level: str) -> list[str]:
    """The captured messages of the loader at one level."""
    return [
        r.getMessage() for r in caplog.records if r.name == "_settings" and r.levelname == level
    ]
