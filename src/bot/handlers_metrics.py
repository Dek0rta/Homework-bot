"""
Продуктовые метрики для владельца бота.

Смысл — видеть, где отваливаются классы, а не гадать. Воронка построена
вокруг единственного вопроса: сколько чатов дошло от «бота добавили» до
«им реально пользуются».
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from src.core import db
from src.core.config import ADMIN_USER_ID

logger = logging.getLogger(__name__)

router = Router()

# Шаги воронки: от установки до регулярного использования
FUNNEL = [
    ("bot_added",           "Бота добавили в чат"),
    ("schedule_recognized", "Расписание распознали"),
    ("schedule_saved",      "Расписание сохранили"),
    ("homework_added",      "Добавили первое ДЗ"),
    ("reminder_subscribed", "Включили напоминания"),
]


def _pct(part: int, whole: int) -> str:
    return f"{part * 100 // whole}%" if whole else "—"


@router.message(Command("metrics"), F.chat.type == "private")
async def cmd_metrics(message: Message):
    """Сводка по продукту. Доступна только владельцу бота."""
    if not ADMIN_USER_ID or message.from_user.id != ADMIN_USER_ID:
        return  # молча: обычному пользователю знать о команде незачем

    week_ago  = (datetime.now() - timedelta(days=7)).isoformat()
    month_ago = (datetime.now() - timedelta(days=30)).isoformat()

    all_time = db.event_counts()
    week     = db.event_counts(week_ago)

    lines = ["📊 <b>Метрики</b>\n"]

    # Воронка — главное, что показывает, где теряются классы
    lines.append("<b>Воронка (всего)</b>")
    base = all_time.get("bot_added", 0)
    for event, label in FUNNEL:
        count = all_time.get(event, 0)
        share = f"  <i>{_pct(count, base)}</i>" if base and event != "bot_added" else ""
        lines.append(f"  {label}: <b>{count}</b>{share}")

    lines.append("")

    # Активность — живёт ли продукт сейчас
    lines.append("<b>За 7 дней</b>")
    lines.append(f"  Активных классов: <b>{db.active_chats(week_ago)}</b>")
    lines.append(f"  Добавлено ДЗ: <b>{week.get('homework_added', 0)}</b>")
    lines.append(f"  Отправлено напоминаний: <b>{week.get('reminder_sent', 0)}</b>")
    lines.append(f"  Правок расписания: <b>{week.get('schedule_edited', 0)}</b>")

    lines.append("")
    lines.append(f"<b>За 30 дней</b>")
    lines.append(f"  Активных классов: <b>{db.active_chats(month_ago)}</b>")

    # Отток — сколько людей отключили напоминания или заблокировали бота
    unsubs  = all_time.get("reminder_unsubscribed", 0)
    blocked = all_time.get("reminder_blocked", 0)
    subs    = all_time.get("reminder_subscribed", 0)
    if subs:
        lines.append("")
        lines.append("<b>Напоминания</b>")
        lines.append(f"  Подписалось: <b>{subs}</b>")
        lines.append(f"  Отписалось: <b>{unsubs}</b>  <i>{_pct(unsubs, subs)}</i>")
        if blocked:
            lines.append(f"  Заблокировали бота: <b>{blocked}</b>")

    # Качество распознавания — насколько модель попадает с первого раза
    recognized = all_time.get("schedule_recognized", 0)
    retried    = all_time.get("schedule_retry", 0)
    failed     = all_time.get("schedule_failed", 0)
    if recognized or failed:
        lines.append("")
        lines.append("<b>Распознавание расписания</b>")
        lines.append(f"  Удачных: <b>{recognized}</b>")
        lines.append(f"  Не распозналось: <b>{failed}</b>")
        lines.append(f"  Пересняли: <b>{retried}</b>")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("events"), F.chat.type == "private")
async def cmd_events(message: Message):
    """Сырые счётчики событий — для отладки."""
    if not ADMIN_USER_ID or message.from_user.id != ADMIN_USER_ID:
        return

    counts = db.event_counts()
    if not counts:
        await message.answer("Событий пока нет.")
        return

    lines = ["<b>Все события</b>\n"]
    for event, count in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"  <code>{event}</code>: {count}")

    await message.answer("\n".join(lines), parse_mode="HTML")
