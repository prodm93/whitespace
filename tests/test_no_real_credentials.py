"""Tests cannot read the real ``.env`` or the machine's AWS credentials."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3
import pytest

from whitespace.config import Config

_SECRET_FIELDS = (
    "neo4j_uri",
    "openrouter_api_key",
    "exa_api_key",
    "firecrawl_api_key",
    "langsmith_api_key",
)


@pytest.mark.protects("tests-cannot-reach-real-services")
def test_an_env_file_in_the_working_directory_is_not_read(tmp_path: Path, monkeypatch: Any) -> None:
    (tmp_path / ".env").write_text("NEO4J_PASSWORD=from-file\n")
    monkeypatch.chdir(tmp_path)

    assert Config().neo4j_password == ""


@pytest.mark.protects("tests-cannot-reach-real-services")
def test_a_bare_config_holds_no_credentials() -> None:
    config = Config()

    filled = [name for name in _SECRET_FIELDS if getattr(config, name)]

    assert filled == []


@pytest.mark.protects("tests-cannot-reach-real-services")
def test_boto3_sees_only_the_fake_test_credentials() -> None:
    credentials = boto3.Session().get_credentials()

    is_fake = credentials is not None and credentials.access_key == "testing"

    assert is_fake


@pytest.mark.protects("tests-cannot-reach-real-services")
def test_a_real_aws_call_is_refused() -> None:
    client = boto3.client("s3", region_name="us-east-1")

    with pytest.raises(AssertionError, match="A test reached a real AWS call"):
        client.list_buckets()
