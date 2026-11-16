"""The API authoriser lets in only a valid Clerk token, and passes on its user and tier."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from _module_loading import load_module
from cryptography.hazmat.primitives.asymmetric import rsa

_HANDLER = Path(__file__).resolve().parents[1] / "deploy" / "aws" / "lambda" / "authoriser"
_ISSUER = "https://clerk.example.test"


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


_SIGNING_KEY = _key()
_OTHER_KEY = _key()


@pytest.fixture()
def authoriser(monkeypatch: Any) -> Any:
    module = load_module("authoriser_handler", _HANDLER / "handler.py")
    keys = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=_SIGNING_KEY.public_key())
    )
    monkeypatch.setattr(module, "_get_jwks_client", lambda: keys)
    monkeypatch.setattr(module, "CLERK_ISSUER", _ISSUER)
    return module


def _token(key: rsa.RSAPrivateKey = _SIGNING_KEY, **claims: Any) -> str:
    payload = {"sub": "user_a", "exp": int(time.time()) + 300, "iss": _ISSUER, **claims}
    return jwt.encode({k: v for k, v in payload.items() if v is not None}, key, algorithm="RS256")


def _event(header: str | None) -> dict:
    return {"headers": {} if header is None else {"authorization": header}}


@pytest.mark.protects("sign-in-token-checked")
@pytest.mark.parametrize(
    "header",
    [
        None,
        "Token abc",
        f"Bearer {_token(exp=int(time.time()) - 60)}",
        f"Bearer {_token(_OTHER_KEY)}",
        f"Bearer {_token(sub=None)}",
    ],
    ids=["no header", "not bearer", "expired", "other key", "no subject"],
)
def test_a_request_without_a_valid_token_is_refused(authoriser: Any, header: str | None) -> None:
    assert authoriser.handler(_event(header), None) == {"isAuthorized": False}


@pytest.mark.protects("sign-in-token-checked")
def test_a_token_of_another_issuer_is_refused_when_the_issuer_is_set(authoriser: Any) -> None:
    token = _token(iss="https://someone-else.example.test")

    assert authoriser.handler(_event(f"Bearer {token}"), None) == {"isAuthorized": False}


@pytest.mark.protects("sign-in-token-checked")
def test_a_failing_key_client_refuses_the_request(authoriser: Any, monkeypatch: Any) -> None:
    def broken() -> Any:
        raise RuntimeError("keys unreachable")

    monkeypatch.setattr(authoriser, "_get_jwks_client", broken)

    assert authoriser.handler(_event(f"Bearer {_token()}"), None) == {"isAuthorized": False}


@pytest.mark.protects("sign-in-token-checked")
def test_a_valid_token_passes_on_its_user_and_tier(authoriser: Any) -> None:
    token = _token(iss=_ISSUER, metadata={"tier": "pro"})

    assert authoriser.handler(_event(f"Bearer {token}"), None) == {
        "isAuthorized": True,
        "context": {"user_id": "user_a", "tier": "pro"},
    }


@pytest.mark.protects("sign-in-token-checked")
def test_a_token_with_no_metadata_gets_the_free_tier(authoriser: Any) -> None:
    result = authoriser.handler(_event(f"Bearer {_token()}"), None)

    assert result["context"] == {"user_id": "user_a", "tier": "free"}


@pytest.mark.protects("sign-in-token-checked")
def test_a_token_with_no_issuer_is_refused(authoriser: Any) -> None:
    assert authoriser.handler(_event(f"Bearer {_token(iss=None)}"), None) == {"isAuthorized": False}


@pytest.mark.protects("sign-in-token-checked")
def test_every_request_is_refused_when_no_issuer_is_configured(
    authoriser: Any, monkeypatch: Any, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(authoriser, "CLERK_ISSUER", "")

    assert authoriser.handler(_event(f"Bearer {_token()}"), None) == {"isAuthorized": False}
    assert [r.levelname for r in caplog.records] == ["ERROR"]
