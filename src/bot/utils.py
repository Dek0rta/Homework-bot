"""Мелкие хелперы для хендлеров: удаление сообщений, форматирование, проверка прав."""

from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram.types import Message

from src.core.constants import DAYS_RU, MONTHS_SHORT


async def safe_delete(message: Message) -> None:
    """Удаляет сообщение, молча игнорируя отсутствие прав или устаревший id."""
    try:
        await message.delete()
    except Exception:
        pass


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
