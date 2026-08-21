"""Shared test doubles for enqueue handler tests."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

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
_reclaim = _load("_reclaim", _ENQUEUE_DIR / "_reclaim.py")
_reset = _load("_reset", _ENQUEUE_DIR / "_reset.py")
enqueue_handler = _load("enqueue_handler", _ENQUEUE_DIR / "handler.py")


def _auth_event(user_id: str, tier: str, body: dict | None = None) -> dict:
    return {
        "requestContext": {"authorizer": {"lambda": {"user_id": user_id, "tier": tier}}},
        "body": json.dumps(body or {"intent": "run gap analysis"}),
    }


def _fake_boto3(*, deny_reserve: bool = False, stale_reset: bool = False) -> MagicMock:
    fb = MagicMock()
    ts = int(time.time()) - 31 * 24 * 3600 if stale_reset else int(time.time())
    fb.resource.return_value.Table.return_value.get_item.return_value = {
        "Item": {"user_id": "u", "last_reset_ts": ts},
    }
    if deny_reserve:
        fb.client.return_value.transact_write_items.side_effect = ClientError(
            {
                "Error": {"Code": "TransactionCanceledException", "Message": ""},
                "CancellationReasons": [
                    {"Code": "ConditionalCheckFailed"},
                    {"Code": "None"},
                ],
            },
            "TransactWriteItems",
        )
    return fb


def _patch(mp: Any, fb: MagicMock) -> None:
    mp.setitem(sys.modules, "boto3", fb)
    mp.setattr(enqueue_handler, "USAGE_TABLE", "usage-t")
    mp.setattr(enqueue_handler, "JOBS_TABLE", "jobs-t")
