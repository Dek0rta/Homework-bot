"""
Проверка конфигурации при старте.

Смысл: типичные ошибки настройки (забытая переменная, включённый в проде
режим отладки) проявляются не при старте, а позже и молча — Mini App просто
не работает. Дешевле проверить всё один раз и написать в лог.

Критичные проблемы останавливают запуск, остальные логируются как
предупреждения — бот при них частично работоспособен.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Конфигурация непригодна для запуска."""


def _check_critical() -> list[str]:
    problems = []

    if not os.getenv("BOT_TOKEN"):
        problems.append("BOT_TOKEN не задан — бот не сможет подключиться к Telegram")

    if not os.getenv("MISTRAL_API_KEY"):
        problems.append("MISTRAL_API_KEY не задан — распознавание ДЗ работать не будет")

    return problems


def _check_warnings() -> list[str]:
    warnings = []

    web_app_url = os.getenv("WEB_APP_URL", "").strip()
    if not web_app_url:
        warnings.append(
            "WEB_APP_URL не задан — кнопки «Открыть приложение» не будет. "
            "Запросы Mini App из клиента Telegram при этом обслуживаются."
        )
    elif not web_app_url.startswith("https://"):
        warnings.append(
            f"WEB_APP_URL={web_app_url!r} не начинается с https:// — "
            "Telegram открывает Mini App только по HTTPS"
        )

    if os.getenv("ALLOW_UNSIGNED_WEBAPP", "").lower() in ("1", "true", "yes"):
        warnings.append(
            "ALLOW_UNSIGNED_WEBAPP включён: REST API принимает любой user_id "
            "без проверки подписи. Допустимо только для локальной разработки."
        )

    if not os.getenv("ADMIN_USER_ID"):
        warnings.append(
            "ADMIN_USER_ID не задан — резервные копии расписания не будут "
            "приходить в личные сообщения, а старый общий токен Google Calendar "
            "не сможет мигрировать"
        )

    return warnings


def run_startup_checks(strict: bool = True) -> None:
    """
    Проверяет окружение. При strict=True критичные проблемы бросают ConfigError.
    """
    for warning in _check_warnings():
        logger.warning("Конфигурация: %s", warning)

    problems = _check_critical()
    if not problems:
        logger.info("Проверка конфигурации пройдена")
        return

    for problem in problems:
        logger.error("Конфигурация: %s", problem)

    if strict:
        raise ConfigError(
            "Не заданы обязательные переменные окружения:\n  - "
            + "\n  - ".join(problems)
            + "\n\nСмотри .env.example."
        )
