"""
Подписка на вечерние напоминания.

Telegram запрещает боту писать первым, поэтому подписаться можно только из
личного чата. Кнопка в группе ведёт туда через deep link, который заодно
передаёт, о каком классе напоминать, — иначе пользователю пришлось бы
выбирать класс вручную.
"""

from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.bot.utils import safe_delete
from src.core import db
from src.core.constants import GROUP_TYPES

logger = logging.getLogger(__name__)

router = Router()

DEFAULT_TIME = "19:00"

# Варианты времени отправки — покрывают вечер после уроков и кружков
TIME_CHOICES = ["17:00", "18:00", "19:00", "20:00", "21:00"]

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _kb_times(current: str) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text=f"{'✅ ' if t == current else ''}{t}",
            callback_data=f"rem:time:{t}",
        )
        for t in TIME_CHOICES
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        row[:3],
        row[3:],
        [InlineKeyboardButton(text="🔕 Отключить", callback_data="rem:off")],
    ])


# ── Вход из группы ───────────────────────────────────────────────────────────

@router.message(Command("reminders"), F.chat.type.in_(GROUP_TYPES))
async def cmd_reminders_group(message: Message):
    """
    В группе только приглашаем в личку: писать напоминания сюда нельзя,
    да и список у каждого свой — с учётом отмеченных заданий.
    """
    me = await message.bot.me()
    link = f"https://t.me/{me.username}?start=rem_{message.chat.id}"

    subscribed = db.count_subscribers(message.chat.id)
    suffix = f"\n\n<i>Уже подключились: {subscribed}</i>" if subscribed else ""

    await message.reply(
        "🌙 <b>Напоминания о домашке</b>\n\n"
        "Вечером пришлю список заданий на завтра — лично, "
        "с учётом того, что ты уже отметил выполненным."
        + suffix,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔔 Включить напоминания", url=link),
        ]]),
    )


# ── Подписка через deep link ─────────────────────────────────────────────────

@router.message(CommandStart(deep_link=True), F.chat.type == "private")
async def cmd_start_deeplink(message: Message, command: CommandObject):
    """Обработка /start rem_<chat_id> — переход по кнопке из группы."""
    payload = command.args or ""

    if not payload.startswith("rem_"):
        return  # не наш deep link — пусть обработает обычный /start

    try:
        chat_id = int(payload[4:])
    except ValueError:
        await message.answer("Не удалось определить класс. Попробуй ещё раз из чата класса.")
        return

    db.subscribe_reminders(message.from_user.id, chat_id, DEFAULT_TIME)
    db.log_event("reminder_subscribed", chat_id=chat_id, user_id=message.from_user.id)

    await message.answer(
        f"🔔 <b>Напоминания включены</b>\n\n"
        f"Каждый вечер в <b>{DEFAULT_TIME}</b> пришлю, что задано на завтра.\n"
        "Если всё уже сделано — писать не буду.\n\n"
        "Изменить время или отключить — /reminders",
        parse_mode="HTML",
        reply_markup=_kb_times(DEFAULT_TIME),
    )


# ── Управление в личке ───────────────────────────────────────────────────────

@router.message(Command("reminders"), F.chat.type == "private")
async def cmd_reminders_private(message: Message):
    sub = db.get_subscription(message.from_user.id)

    if not sub or not sub["enabled"]:
        # Класс, если он известен, — тогда в напоминании будут и его задания
        chats = db.get_chats_for_user(message.from_user.id)
        db.subscribe_reminders(message.from_user.id, chats[0] if chats else message.from_user.id, DEFAULT_TIME)
        db.log_event("reminder_subscribed", user_id=message.from_user.id, payload={"from": "private"})
        await message.answer(
            f"🔔 <b>Напоминания включены</b>\n\n"
            f"Каждый вечер в <b>{DEFAULT_TIME}</b> пришлю, что задано на завтра.\n"
            "Если всё уже сделано — писать не буду.\n\n"
            "Выбери другое время или отключи:",
            parse_mode="HTML",
            reply_markup=_kb_times(DEFAULT_TIME),
        )
        return

    await message.answer(
        f"🔔 Напоминания включены, время — <b>{sub['send_at']}</b>.\n\n"
        "Выбери другое время или отключи:",
        parse_mode="HTML",
        reply_markup=_kb_times(sub["send_at"]),
    )


@router.message(Command("reminders_off"), F.chat.type == "private")
async def cmd_reminders_off(message: Message):
    db.unsubscribe_reminders(message.from_user.id)
    db.log_event("reminder_unsubscribed", user_id=message.from_user.id)
    await message.answer(
        "🔕 Напоминания отключены.\n"
        "Включить снова — /reminders"
    )


@router.callback_query(F.data.startswith("rem:time:"))
async def cb_set_time(call: CallbackQuery):
    new_time = call.data.split(":", 2)[2]

    if not _TIME_RE.match(new_time):
        await call.answer("Некорректное время", show_alert=True)
        return

    sub = db.get_subscription(call.from_user.id)
    if not sub:
        await call.answer("Сначала включи напоминания — /reminders", show_alert=True)
        return

    db.subscribe_reminders(call.from_user.id, sub["chat_id"], new_time)
    await call.answer(f"Буду писать в {new_time}")

    await call.message.edit_text(
        f"🔔 Напоминания включены, время — <b>{new_time}</b>.",
        parse_mode="HTML",
        reply_markup=_kb_times(new_time),
    )


@router.callback_query(F.data == "rem:off")
async def cb_disable(call: CallbackQuery):
    db.unsubscribe_reminders(call.from_user.id)
    db.log_event("reminder_unsubscribed", user_id=call.from_user.id)
    await call.answer("Отключено")
    await call.message.edit_text(
        "🔕 Напоминания отключены.\n"
        "Включить снова — /reminders",
        parse_mode="HTML",
    )
