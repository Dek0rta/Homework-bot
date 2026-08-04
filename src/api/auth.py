"""
Проверка подлинности Telegram Mini App initData.

Telegram подписывает initData HMAC-ключом, производным от токена бота.
Проверка подписи — единственный способ доверять user_id, который прислал
фронтенд: без неё любой может выдать себя за другого ученика.

Алгоритм (документация Telegram, «Validating data received via the Mini App»):
  secret_key   = HMAC_SHA256(key="WebAppData", msg=bot_token)
  expected     = HMAC_SHA256(key=secret_key, msg=data_check_string)
  data_check_string — пары "key=value" без hash, отсортированные по ключу,
  соединённые "\n".
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import parse_qsl

from src.core.config import BOT_TOKEN

logger = logging.getLogger(__name__)

# Максимальный возраст initData. Ограничивает окно для replay-атаки
# перехваченной подписью.
MAX_AGE_SECONDS = 24 * 60 * 60

# Аварийный выключатель для локальной разработки без Telegram-клиента.
# В проде оставлять выключенным: при "1" API принимает любой user_id на слово.
ALLOW_UNSIGNED = os.getenv("ALLOW_UNSIGNED_WEBAPP", "").lower() in ("1", "true", "yes")


class AuthError(Exception):
    """initData отсутствует, просрочена или подпись не сходится."""


def _data_check_string(pairs: list[tuple[str, str]]) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(pairs) if k != "hash")


def verify_init_data(init_data: str) -> dict:
    """
    Проверяет подпись initData и возвращает распакованный объект user.
    Бросает AuthError, если данные подделаны, просрочены или отсутствуют.
    """
    if not init_data:
        raise AuthError("initData отсутствует")
    if not BOT_TOKEN:
        raise AuthError("BOT_TOKEN не сконфигурирован — проверка невозможна")

    pairs        = parse_qsl(init_data, keep_blank_values=True)
    received_map = dict(pairs)
    received_hash = received_map.get("hash", "")
    if not received_hash:
        raise AuthError("в initData нет поля hash")

    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected   = hmac.new(
        secret_key, _data_check_string(pairs).encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise AuthError("подпись initData не сходится")

    # Защита от повторного использования старой подписи
    try:
        auth_date = int(received_map.get("auth_date", "0"))
    except ValueError:
        raise AuthError("некорректное поле auth_date")
    if auth_date <= 0 or time.time() - auth_date > MAX_AGE_SECONDS:
        raise AuthError("initData просрочена")

    try:
        user = json.loads(received_map.get("user", "{}"))
    except json.JSONDecodeError:
        raise AuthError("некорректное поле user")

    if not user.get("id"):
        raise AuthError("в initData нет user.id")

    return user


def authenticate(request) -> int:
    """
    Достаёт и проверяет initData из заголовка X-Telegram-Init-Data.
    Возвращает доверенный user_id.

    При ALLOW_UNSIGNED=1 (только для локальной разработки) пропускает
    проверку и берёт user_id из заголовка X-Debug-User-Id.
    """
    init_data = request.headers.get("X-Telegram-Init-Data", "")

    if ALLOW_UNSIGNED and not init_data:
        logger.warning("ALLOW_UNSIGNED_WEBAPP включён — запрос принят без подписи")
        return int(request.headers.get("X-Debug-User-Id", 0) or 0)

    return int(verify_init_data(init_data)["id"])
