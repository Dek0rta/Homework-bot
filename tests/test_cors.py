"""
Тесты CORS-политики REST API.

Ключевое требование: незаданный WEB_APP_URL не должен ломать запросы из
клиента Telegram, но и произвольный сторонний сайт не должен получать
доступ к API от имени пользователя.
"""

from __future__ import annotations

import importlib

import pytest

TELEGRAM_ORIGIN = "https://web.telegram.org"
APP_ORIGIN      = "https://app.example.com"
EVIL_ORIGIN     = "https://evil.example.com"


@pytest.fixture
def api(monkeypatch):
    """Модуль API с заданным WEB_APP_URL."""
    def _load(web_app_url: str | None):
        if web_app_url is None:
            monkeypatch.delenv("WEB_APP_URL", raising=False)
        else:
            monkeypatch.setenv("WEB_APP_URL", web_app_url)
        from src.api import webapp_api
        importlib.reload(webapp_api)
        return webapp_api
    return _load


def test_configured_origin_is_allowed(api):
    mod = api(APP_ORIGIN)
    assert APP_ORIGIN in mod.allowed_origins()


def test_path_is_stripped_from_configured_url(api):
    """WEB_APP_URL с путём даёт корректный Origin — путь в Origin недопустим."""
    mod = api(f"{APP_ORIGIN}/some/path")
    assert APP_ORIGIN in mod.allowed_origins()
    assert f"{APP_ORIGIN}/some/path" not in mod.allowed_origins()


def test_trailing_slash_is_normalized(api):
    mod = api(f"{APP_ORIGIN}/")
    assert APP_ORIGIN in mod.allowed_origins()


def test_telegram_origins_allowed_without_config(api):
    """
    Регрессия: раньше пустой WEB_APP_URL давал Origin "null",
    и Mini App получал отказ на любой запрос.
    """
    mod = api(None)
    assert TELEGRAM_ORIGIN in mod.allowed_origins()


def test_telegram_origins_allowed_alongside_config(api):
    mod = api(APP_ORIGIN)
    origins = mod.allowed_origins()
    assert APP_ORIGIN in origins
    assert TELEGRAM_ORIGIN in origins


def test_unknown_origin_rejected(api):
    mod = api(APP_ORIGIN)
    assert EVIL_ORIGIN not in mod.allowed_origins()


def test_unknown_origin_rejected_without_config(api):
    mod = api(None)
    assert EVIL_ORIGIN not in mod.allowed_origins()


def test_wildcard_is_never_allowed(api):
    """Звёздочка означала бы доступ для любого сайта — её быть не должно."""
    for url in (APP_ORIGIN, None):
        assert "*" not in api(url).allowed_origins()


def test_malformed_url_does_not_crash(api):
    """Мусор в WEB_APP_URL не должен ронять запуск — падаем к origin'ам Telegram."""
    mod = api("не-ссылка")
    assert TELEGRAM_ORIGIN in mod.allowed_origins()
