"""Unit tests for reservation primitives: cancellation, two-path, constants."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

_ROOT = Path(__file__).parent.parent
_ENQUEUE_DIR = _ROOT / "deploy" / "aws" / "lambda" / "orchestrate_enqueue"


def _load(name: str, path: Path) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_txn = _load("_txn", _ENQUEUE_DIR / "_txn.py")
_reservation = _load("_reservation", _ENQUEUE_DIR / "_reservation.py")


# --- cancellation_reasons ---


def test_safe_codes_pass_through() -> None:
    exc = MagicMock()
    exc.response = {
        "CancellationReasons": [
            {"Code": "ConditionalCheckFailed"},
            {"Code": "None"},
        ]
    }
    reasons = _reservation.cancellation_reasons(exc)
    assert len(reasons) == 2
    assert reasons[0]["Code"] == "ConditionalCheckFailed"


def test_transient_code_raises() -> None:
    exc = ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": ""},
            "CancellationReasons": [
                {"Code": "None"},
                {"Code": "TransactionConflict"},
            ],
        },
        "TransactWriteItems",
    )
    with pytest.raises(ClientError):
        _reservation.cancellation_reasons(exc)


def test_throttling_code_raises() -> None:
    exc = ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": ""},
            "CancellationReasons": [
                {"Code": "ThrottlingError"},
                {"Code": "None"},
            ],
        },
        "TransactWriteItems",
    )
    with pytest.raises(ClientError):
        _reservation.cancellation_reasons(exc)


# --- two-path reserve ---


def test_modern_path_success(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    client = fb.client.return_value
    result = _reservation.reserve_slot("u1", "j1", 10, "usage", "jobs", "us-east-1")
    assert result == "reserved"
    assert client.transact_write_items.call_count == 1


def test_legacy_fallback_on_missing_used_count(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    client = fb.client.return_value
    calls = [0]

    def _txn(**kw: Any) -> None:
        calls[0] += 1
        if calls[0] == 1:
            raise ClientError(
                {
                    "Error": {"Code": "TransactionCanceledException", "Message": ""},
                    "CancellationReasons": [
                        {"Code": "ConditionalCheckFailed"},
                        {"Code": "None"},
                    ],
                },
                "TransactWriteItems",
            )

    client.transact_write_items.side_effect = _txn
    fb.resource.return_value.Table.return_value.get_item.return_value = {
        "Item": {"user_id": "u1"},
    }
    result = _reservation.reserve_slot("u1", "j1", 10, "usage", "jobs", "us-east-1")
    assert result == "reserved"
    assert calls[0] == 2


def test_denied_when_at_cap(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    client = fb.client.return_value
    client.transact_write_items.side_effect = ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": ""},
            "CancellationReasons": [
                {"Code": "ConditionalCheckFailed"},
                {"Code": "None"},
            ],
        },
        "TransactWriteItems",
    )
    fb.resource.return_value.Table.return_value.get_item.return_value = {
        "Item": {"user_id": "u1", "used_count": 10},
    }
    result = _reservation.reserve_slot("u1", "j1", 10, "usage", "jobs", "us-east-1")
    assert result == "cap_reached"


# --- contention exhaustion ---


def test_raises_on_exhausted_contention(monkeypatch: Any) -> None:
    fb = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", fb)
    client = fb.client.return_value
    client.transact_write_items.side_effect = ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": ""},
            "CancellationReasons": [
                {"Code": "ConditionalCheckFailed"},
                {"Code": "None"},
            ],
        },
        "TransactWriteItems",
    )
    fb.resource.return_value.Table.return_value.get_item.return_value = {
        "Item": {"user_id": "u1", "used_count": 5},
    }
    with pytest.raises(RuntimeError, match="Unable to verify"):
        _reservation.reserve_slot("u1", "j1", 10, "usage", "jobs", "us-east-1")


# --- reservation TTL ---


def test_reservation_ttl_is_48_hours() -> None:
    assert _reservation.RESERVATION_TTL_SECONDS == 48 * 3600
