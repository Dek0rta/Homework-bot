"""Тесты проверки конфигурации при старте."""

from __future__ import annotations

import pytest

from src.core.startup_checks import ConfigError, run_startup_checks

REQUIRED = {"BOT_TOKEN": "123:abc", "MISTRAL_API_KEY": "key"}


@pytest.fixture
def env(monkeypatch):
    """Чистое окружение, в которое тест докладывает только нужное."""
    for key in ("BOT_TOKEN", "MISTRAL_API_KEY", "WEB_APP_URL",
                "ADMIN_USER_ID", "ALLOW_UNSIGNED_WEBAPP"):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_passes_with_required_vars(env):
    for k, v in REQUIRED.items():
        env.setenv(k, v)
    run_startup_checks()  # не должно бросать


def test_missing_bot_token_fails(env):
    env.setenv("MISTRAL_API_KEY", "key")
    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        run_startup_checks()


def test_missing_mistral_key_fails(env):
    env.setenv("BOT_TOKEN", "123:abc")
    with pytest.raises(ConfigError, match="MISTRAL_API_KEY"):
        run_startup_checks()


def test_error_lists_all_missing_vars(env):
    with pytest.raises(ConfigError) as exc:
        run_startup_checks()
    message = str(exc.value)
    assert "BOT_TOKEN" in message
    assert "MISTRAL_API_KEY" in message


def test_non_strict_mode_does_not_raise(env):
    run_startup_checks(strict=False)


def test_optional_vars_only_warn(env, caplog):
    """Отсутствие WEB_APP_URL — предупреждение, не отказ запуска."""
    for k, v in REQUIRED.items():
        env.setenv(k, v)
    with caplog.at_level("WARNING"):
        run_startup_checks()
    assert "WEB_APP_URL" in caplog.text


def test_unsigned_webapp_flag_warns(env, caplog):
    """Режим без проверки подписи обязан быть заметен в логе."""
    for k, v in REQUIRED.items():
        env.setenv(k, v)
    env.setenv("ALLOW_UNSIGNED_WEBAPP", "1")
    with caplog.at_level("WARNING"):
        run_startup_checks()
    assert "ALLOW_UNSIGNED_WEBAPP" in caplog.text


def test_http_web_app_url_warns(env, caplog):
    for k, v in REQUIRED.items():
        env.setenv(k, v)
    env.setenv("WEB_APP_URL", "http://insecure.example.com")
    with caplog.at_level("WARNING"):
        run_startup_checks()
    assert "https" in caplog.text.lower()
