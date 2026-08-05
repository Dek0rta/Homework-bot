"""Мелкие хелперы для хендлеров: удаление сообщений, форматирование, проверка прав."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from src.core.constants import DAYS_RU, MONTHS_SHORT

logger = logging.getLogger(__name__)


async def safe_delete(message: Message) -> None:
    """Удаляет сообщение, игнорируя отсутствие прав или устаревший id."""
    try:
        await message.delete()
    except TelegramAPIError as e:
        logger.debug("Не удалось удалить сообщение %s: %s", message.message_id, e)


async def delete_after(message: Message, delay: int = 10) -> None:
    """Удаляет сообщение через delay секунд — для служебных уведомлений."""
    await asyncio.sleep(delay)
    await safe_delete(message)


def fmt_due_date(iso: str) -> str:
    """'YYYY-MM-DD' → 'Понедельник, 3 мар'."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{DAYS_RU[d.weekday()]}, {d.day} {MONTHS_SHORT[d.month - 1]}"
    except Exception:
        return iso


async def is_chat_admin(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False
