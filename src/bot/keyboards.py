"""Построение клавиатур: главное меню и редактор расписания."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from src.core.config import WEB_APP_URL
from src.core.constants import (
    BTN_HOMEWORK,
    BTN_SCHEDULE,
    BTN_SET_SCHEDULE,
    BTN_STATS,
    BTN_WEBAPP,
    DAYS_SHORT,
    LESSON_TIMES,
)


def build_main_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_SET_SCHEDULE), KeyboardButton(text=BTN_SCHEDULE)],
        [KeyboardButton(text=BTN_HOMEWORK),     KeyboardButton(text=BTN_STATS)],
    ]
    if WEB_APP_URL:
        rows.append([KeyboardButton(text=BTN_WEBAPP, web_app=WebAppInfo(url=WEB_APP_URL))])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Отправь фото или текст с ДЗ...",
    )


MAIN_KB = build_main_kb()


# ── Временное расписание в FSM ────────────────────────────────────────────────
#
# Формат temp: {day_str: {slot_str: subject}}
#   day_str  — "0".."6"  (0=Пн)
#   slot_str — "0".."7"  (номер урока, 0-based)
#   subject  — название предмета или "" (пусто)


def temp_has_lessons(temp: dict, day: int) -> bool:
    return any(v for v in temp.get(str(day), {}).values())


def temp_get_subject(temp: dict, day: int, slot: int) -> str:
    return temp.get(str(day), {}).get(str(slot), "")


def temp_set_subject(temp: dict, day: int, slot: int, subject: str) -> None:
    temp.setdefault(str(day), {})[str(slot)] = subject


# ── Клавиатуры редактора расписания ───────────────────────────────────────────

def kb_days(temp: dict) -> InlineKeyboardMarkup:
    """Экран выбора дня: 7 кнопок + Сохранить."""
    buttons = []
    for i, name in enumerate(DAYS_SHORT):
        mark = "✅" if temp_has_lessons(temp, i) else "◻️"
        buttons.append(InlineKeyboardButton(text=f"{mark} {name}", callback_data=f"sched:day:{i}"))

    keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    keyboard.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="sched:save")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_lessons(day: int, temp: dict) -> InlineKeyboardMarkup:
    """Экран дня: кнопки 1–8 урок по 2 в ряд."""
    buttons = []
    for slot in range(8):
        subject = temp_get_subject(temp, day, slot)
        label   = f"{slot + 1} ✅ {subject}" if subject else f"{slot + 1} урок  {LESSON_TIMES[slot]}"
        buttons.append(
            InlineKeyboardButton(text=label, callback_data=f"sched:slot:{day}:{slot}")
        )

    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="◀️ К дням", callback_data="sched:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
