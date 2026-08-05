"""
Обновление OAuth-токена Google Calendar.

Раньше любое исключение из creds.refresh() удаляло токен из БД, поэтому
разовый сбой сети разлогинивал ученика из календаря навсегда. Токен теперь
удаляется только когда Google действительно отозвал доступ.
"""

from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError

from src.services import calendar as cal

TOKEN_JSON = (
    '{"token": "t", "refresh_token": "r", '
    '"client_id": "c", "client_secret": "s"}'
)


@pytest.fixture
def expired_creds():
    """Просроченные credentials с refresh_token — их положено обновлять."""
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "r"
    return creds


def _get_credentials(creds, refresh_exc):
    """
    Прогоняет get_credentials() с подменённой БД. Возвращает
    (результат, был ли удалён токен).
    """
    creds.refresh.side_effect = refresh_exc
    deleted: list[int] = []

    with patch.object(cal.db, "get_calendar_token", return_value=TOKEN_JSON), \
         patch.object(cal.db, "get_calendar_id", return_value=None), \
         patch.object(cal.db, "save_calendar_token"), \
         patch.object(cal.db, "delete_calendar_token", side_effect=deleted.append), \
         patch.object(cal.Credentials, "from_authorized_user_info", return_value=creds):
        result = cal.get_credentials(42)

    return result, bool(deleted)


def test_network_error_keeps_token(expired_creds):
    """Сеть отвалилась — токен исправен и должен остаться в БД."""
    result, deleted = _get_credentials(expired_creds, ConnectionError("network down"))

    assert result is None
    assert not deleted, "разовый сбой сети не должен отвязывать календарь"


def test_timeout_keeps_token(expired_creds):
    result, deleted = _get_credentials(expired_creds, TimeoutError("timed out"))

    assert result is None
    assert not deleted


def test_revoked_access_deletes_token(expired_creds):
    """Google отозвал доступ — токен больше не пригоден, храним зря."""
    result, deleted = _get_credentials(expired_creds, RefreshError("revoked"))

    assert result is None
    assert deleted, "отозванный токен нужно удалить"


def test_successful_refresh_returns_creds(expired_creds):
    result, deleted = _get_credentials(expired_creds, None)

    assert result is expired_creds
    assert not deleted


def test_no_token_returns_none():
    with patch.object(cal.db, "get_calendar_token", return_value=None):
        assert cal.get_credentials(42) is None


def test_corrupted_token_returns_none():
    """Битый JSON в БД — не падаем, просим переавторизоваться."""
    with patch.object(cal.db, "get_calendar_token", return_value="{not json"):
        assert cal.get_credentials(42) is None


def test_valid_token_skips_refresh():
    creds = MagicMock()
    creds.valid = True

    with patch.object(cal.db, "get_calendar_token", return_value=TOKEN_JSON), \
         patch.object(cal.Credentials, "from_authorized_user_info", return_value=creds):
        assert cal.get_credentials(42) is creds

    creds.refresh.assert_not_called()
