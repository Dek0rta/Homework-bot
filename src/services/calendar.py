"""
Google Calendar на каждого пользователя.

Токен хранится в таблице user_calendar_tokens и привязан к user_id, поэтому
ДЗ каждого ученика попадает в его собственный календарь. Раньше токен был
один на весь бот (data/token.json) — все события уходили в календарь того,
кто авторизовался первым.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.core import db
from src.core.config import CREDENTIALS_PATH, TIMEZONE, TOKEN_PATH

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Длительность события ДЗ в календаре
EVENT_DURATION_MINUTES = 45


def migrate_legacy_token(owner_user_id: int | None) -> bool:
    """
    Переносит единственный старый data/token.json в таблицу как токен
    администратора. Вызывается один раз при старте.

    Возвращает True, если перенос состоялся. Файл после переноса удаляется,
    чтобы он не выглядел как «общий» токен и не сбивал с толку.
    """
    if not owner_user_id or not os.path.exists(TOKEN_PATH):
        return False
    if db.has_calendar_token(owner_user_id):
        return False  # у администратора уже есть токен в БД

    try:
        with open(TOKEN_PATH, encoding="utf-8") as f:
            token_json = f.read()
        json.loads(token_json)  # проверяем, что это валидный JSON
    except Exception:
        logger.warning("Не удалось прочитать legacy token.json — пропускаю миграцию")
        return False

    db.save_calendar_token(owner_user_id, token_json)
    try:
        os.remove(TOKEN_PATH)
    except OSError:
        pass
    logger.info("Legacy token.json перенесён в БД для user_id=%s", owner_user_id)
    return True


def get_credentials(user_id: int) -> Credentials | None:
    """
    Credentials конкретного пользователя, при необходимости обновлённые.
    None — если пользователь не авторизован или токен отозван.
    """
    raw = db.get_calendar_token(user_id)
    if not raw:
        return None

    try:
        creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    except Exception:
        logger.warning("Повреждённый токен у user_id=%s — требуется повторная авторизация", user_id)
        return None

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            # Доступ отозван в Google-аккаунте — токен больше не пригоден
            logger.info("Не удалось обновить токен user_id=%s — удаляю", user_id)
            db.delete_calendar_token(user_id)
            return None
        db.save_calendar_token(user_id, creds.to_json(), db.get_calendar_id(user_id))
        return creds

    return None


def is_connected(user_id: int) -> bool:
    return get_credentials(user_id) is not None


def disconnect(user_id: int) -> None:
    db.delete_calendar_token(user_id)


def credentials_file_exists() -> bool:
    """Есть ли credentials.json приложения — общий для всех пользователей."""
    return os.path.exists(CREDENTIALS_PATH)


def get_auth_url() -> tuple[str, InstalledAppFlow]:
    """(url, flow) для OAuth через copy-paste кода."""
    flow = InstalledAppFlow.from_client_secrets_file(
        CREDENTIALS_PATH,
        SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return auth_url, flow


def exchange_code(user_id: int, flow: InstalledAppFlow, code: str) -> Credentials:
    """Обменивает код из браузера на токен и сохраняет его за пользователем."""
    flow.fetch_token(code=code)
    creds = flow.credentials
    db.save_calendar_token(user_id, creds.to_json())
    return creds


async def add_homework_event(user_id: int, subject: str, task: str, lesson_dt: datetime) -> str:
    """
    Создаёт событие в календаре пользователя и возвращает ссылку на него.
    Блокирующие вызовы Google API уходят в executor, чтобы не держать event loop.

    Бросает RuntimeError("not_authorized"), если пользователь не подключил календарь.
    """
    end_dt = lesson_dt + timedelta(minutes=EVENT_DURATION_MINUTES)
    event_body = {
        "summary":     f"📚 {subject}: {task}",
        "description": f"Предмет: {subject}\nЗадание: {task}",
        "start": {"dateTime": lesson_dt.isoformat(), "timeZone": TIMEZONE},
        "end":   {"dateTime": end_dt.isoformat(),    "timeZone": TIMEZONE},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 1440},
            ],
        },
        "colorId": "9",
    }

    def _sync_insert():
        creds = get_credentials(user_id)
        if not creds:
            raise RuntimeError("not_authorized")
        service = build("calendar", "v3", credentials=creds)
        return service.events().insert(
            calendarId=db.get_calendar_id(user_id),
            body=event_body,
        ).execute()

    loop   = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _sync_insert)
    return result.get("htmlLink", "")
