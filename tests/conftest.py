"""Shared fixtures for upload Lambda handler tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from _fake_dynamodb import FakeDynamoDB

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
