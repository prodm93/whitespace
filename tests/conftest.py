"""Shared fixtures for upload Lambda handler tests, and the guards that keep every test
away from real services.

It also holds the ``runtime`` fixture of the SaaS pipeline function's tests, and the hooks
that count, for each risk register item, the passed tests marked ``protects(<item>)``; the
counts are written to ``protected.json`` in the root directory at the end of the session.

The guards: ``Config`` never reads an env file; each test runs without the Neo4j, model,
search and AWS profile variables, with fake AWS credentials, and with every botocore client
call refused.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import botocore.client
import pytest
from _fake_dynamodb import FakeDynamoDB

from whitespace.config import Config

Config.model_config["env_file"] = None

_REMOVED_VARIABLES = (
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "AURA_INSTANCEID",
    "AURA_INSTANCENAME",
    "OPENROUTER_API_KEY",
    "EXA_API_KEY",
    "FIRECRAWL_API_KEY",
    "LANGSMITH_API_KEY",
    "CREDS_ENV_FILE",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
)


def _refuse_aws_call(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("A test reached a real AWS call")


@pytest.fixture(autouse=True)
def _no_real_services(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in _REMOVED_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    missing = str(tmp_path / "no-aws-files" / "missing")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", missing)
    monkeypatch.setenv("AWS_CONFIG_FILE", missing)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(botocore.client.BaseClient, "_make_api_call", _refuse_aws_call)


_PASSED_PER_ITEM: Counter[str] = Counter()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        for marker in item.iter_markers("protects"):
            item.user_properties.append(("protects", marker.args[0]))


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when == "call" and report.passed:
        for key, value in report.user_properties:
            if key == "protects":
                _PASSED_PER_ITEM[str(value)] += 1


def pytest_sessionfinish(session: pytest.Session) -> None:
    path = session.config.rootpath / "protected.json"
    path.write_text(json.dumps(dict(sorted(_PASSED_PER_ITEM.items())), indent=2) + "\n")


@pytest.fixture()
def runtime(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> Any:
    """The SaaS pipeline function's runtime module, with fake kept clients and pipeline."""
    from _saas_helpers import fake_runtime

    return fake_runtime(monkeypatch, request)


_ROOT = Path(__file__).resolve().parent.parent
_UPLOAD_URL_DIR = str(_ROOT / "deploy" / "aws" / "lambda" / "upload_url")
_UPLOAD_CONFIRM_DIR = str(_ROOT / "deploy" / "aws" / "lambda" / "upload_confirm")


def _load_module(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def fake_dynamo():
    return FakeDynamoDB()


@pytest.fixture()
def _patch_env(monkeypatch):
    monkeypatch.setenv("UPLOADS_BUCKET", "test-uploads")
    monkeypatch.setenv("USAGE_TABLE", "test-usage")
    monkeypatch.setenv("RESERVATIONS_TABLE", "test-reservations")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@pytest.fixture()
def _mock_boto3(fake_dynamo):
    mock_boto = MagicMock()
    s3_mock = MagicMock()
    s3_mock.generate_presigned_post.return_value = {
        "url": "https://s3.example.com",
        "fields": {"key": "test"},
    }

    def _client(service, **kwargs):
        if service == "dynamodb":
            return fake_dynamo
        return s3_mock

    mock_boto.client.side_effect = _client

    with patch.dict(sys.modules, {"boto3": mock_boto}):
        yield mock_boto


@pytest.fixture()
def upload_url_handler(_mock_boto3, _patch_env):
    return _load_module(
        "upload_url_handler",
        Path(_UPLOAD_URL_DIR) / "handler.py",
    )


@pytest.fixture()
def upload_confirm_handler(_mock_boto3, _patch_env):
    return _load_module(
        "upload_confirm_handler",
        Path(_UPLOAD_CONFIRM_DIR) / "handler.py",
    )
