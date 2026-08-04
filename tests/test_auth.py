"""Тесты проверки подписи Telegram initData."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from src.api import auth
from src.api.auth import AuthError, verify_init_data

BOT_TOKEN = "123456:TEST-TOKEN-FOR-UNIT-TESTS"


def make_init_data(user_id: int = 42, auth_date: int | None = None, token: str = BOT_TOKEN) -> str:
    """Собирает корректно подписанную initData — как это делает Telegram."""
    fields = {
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAEtest",
    }
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture(autouse=True)
def _patch_token(monkeypatch):
    monkeypatch.setattr(auth, "BOT_TOKEN", BOT_TOKEN)


def test_valid_init_data_returns_user():
    user = verify_init_data(make_init_data(user_id=777))
    assert user["id"] == 777


def test_empty_init_data_rejected():
    with pytest.raises(AuthError):
        verify_init_data("")


def test_tampered_user_id_rejected():
    """Подмена user_id без пересчёта hash должна проваливать проверку."""
    raw = make_init_data(user_id=42)
    tampered = raw.replace("%22id%22%3A42", "%22id%22%3A999")
    assert tampered != raw
    with pytest.raises(AuthError):
        verify_init_data(tampered)


def test_wrong_token_signature_rejected():
    """Подпись чужим токеном не проходит."""
    with pytest.raises(AuthError):
        verify_init_data(make_init_data(token="999:WRONG-TOKEN"))


def test_missing_hash_rejected():
    with pytest.raises(AuthError):
        verify_init_data("user=%7B%22id%22%3A1%7D&auth_date=1700000000")


def test_expired_init_data_rejected():
    old = int(time.time()) - auth.MAX_AGE_SECONDS - 60
    with pytest.raises(AuthError):
        verify_init_data(make_init_data(auth_date=old))


def test_fresh_init_data_within_max_age_accepted():
    recent = int(time.time()) - auth.MAX_AGE_SECONDS + 60
    assert verify_init_data(make_init_data(user_id=5, auth_date=recent))["id"] == 5
