"""
Резервное копирование критичных данных (расписание, предметы групп, привязки).

Зачем: на бесплатных/эфемерных тарифах хостинга диск с SQLite пересоздаётся при
редеплое. Бэкап хранится как переменная окружения SCHEDULE_BACKUP и
автоматически восстанавливается при старте, если БД пуста.

Каналы доставки бэкапа, в порядке приоритета:
  1. Railway GraphQL API — обновляет SCHEDULE_BACKUP автоматически.
  2. Личное сообщение администратору (ADMIN_USER_ID).
  3. Запись в лог — всегда, как последний рубеж.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from src.core import db
from src.core.config import ADMIN_USER_ID

logger = logging.getLogger(__name__)


def make_backup_json() -> str:
    return json.dumps(db.export_critical_data(), ensure_ascii=False, separators=(",", ":"))


async def _push_to_railway(backup_json: str) -> bool:
    """
    Обновляет переменную SCHEDULE_BACKUP через Railway GraphQL API.
    Требует RAILWAY_TOKEN; остальные идентификаторы Railway подставляет сам.
    Возвращает True при успехе.
    """
    import urllib.request as _req

    token      = os.getenv("RAILWAY_TOKEN")
    project_id = os.getenv("RAILWAY_PROJECT_ID")
    env_id     = os.getenv("RAILWAY_ENVIRONMENT_ID")
    service_id = os.getenv("RAILWAY_SERVICE_ID")

    if not all([token, project_id, env_id, service_id]):
        return False  # не Railway-окружение или токен не задан

    payload = json.dumps({
        "query": "mutation($i:VariableUpsertInput!){variableUpsert(input:$i)}",
        "variables": {"i": {
            "projectId":     project_id,
            "environmentId": env_id,
            "serviceId":     service_id,
            "name":          "SCHEDULE_BACKUP",
            "value":         backup_json,
        }},
    }).encode()

    request = _req.Request(
        "https://backboard.railway.app/graphql/v2",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        loop   = asyncio.get_running_loop()
        body   = await loop.run_in_executor(None, lambda: _req.urlopen(request, timeout=10).read())
        result = json.loads(body)
        if "errors" not in result:
            logger.info("SCHEDULE_BACKUP автоматически обновлён в Railway")
            return True
        logger.warning("Railway API вернул ошибку: %s", result["errors"])
    except Exception as e:
        logger.warning("Railway API недоступен: %s", e)
    return False


async def save_backup(bot) -> None:
    """Сохраняет бэкап после изменения расписания по всем доступным каналам."""
    from aiogram.types import BufferedInputFile

    backup_json = make_backup_json()
    data        = json.loads(backup_json)
    n_lessons   = len(data.get("schedule", []))
    n_subj      = len(data.get("chat_subjects", []))

    if await _push_to_railway(backup_json):
        return

    if ADMIN_USER_ID:
        try:
            text = (
                "💾 <b>Сохрани резервную копию!</b>\n\n"
                f"Уроков: <b>{n_lessons}</b>  |  Предметов: <b>{n_subj}</b>\n\n"
                "Скопируй и вставь в переменную окружения <code>SCHEDULE_BACKUP</code>:\n\n"
                f"<code>{backup_json}</code>"
            )
            if len(text) <= 4096:
                await bot.send_message(ADMIN_USER_ID, text, parse_mode="HTML")
            else:
                await bot.send_document(
                    ADMIN_USER_ID,
                    BufferedInputFile(backup_json.encode(), filename="schedule_backup.json"),
                    caption=(
                        "💾 Резервная копия. Сохрани содержимое файла "
                        "как переменную SCHEDULE_BACKUP."
                    ),
                )
        except Exception:
            pass  # бот заблокирован — лог ниже покроет

    logger.info("SCHEDULE_BACKUP_VALUE=%s", backup_json)


def restore_if_empty() -> None:
    """Восстанавливает данные из SCHEDULE_BACKUP, если БД пуста после редеплоя."""
    backup_env = os.getenv("SCHEDULE_BACKUP")
    if not backup_env or not db.is_db_empty():
        return
    try:
        count = db.import_critical_data(json.loads(backup_env))
        logger.info("Восстановлено %d записей из SCHEDULE_BACKUP", count)
    except Exception:
        logger.exception("Ошибка восстановления из SCHEDULE_BACKUP")
