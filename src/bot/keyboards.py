"""Построение клавиатур: главное меню, редактор расписания, выбор дня сдачи ДЗ."""

from __future__ import annotations

from datetime import datetime, timedelta

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from src.core.config import WEB_APP_URL
from src.core.constants import (
    BTN_CALENDAR,
    BTN_SCHEDULE,
    BTN_SET_SCHEDULE,
    BTN_STATS,
    BTN_WEBAPP,
    DAYS_RU,
    DAYS_SHORT,
    LESSON_TIMES,
    MONTHS_SHORT,
)
from src.services import schedule as sched_module


def build_main_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_SET_SCHEDULE), KeyboardButton(text=BTN_SCHEDULE)],
        [KeyboardButton(text=BTN_CALENDAR),     KeyboardButton(text=BTN_STATS)],
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


# ── Клавиатуры выбора дня сдачи ДЗ ────────────────────────────────────────────

def kb_hw_due_day(hw_key: int, entries: list[dict] | None = None) -> InlineKeyboardMarkup:
    """
    Кнопки выбора дня сдачи ДЗ (групповой сценарий).
    entries — слоты расписания по предмету (day_of_week + start_time).
      Если переданы — показываем ближайшие 2 даты для каждого слота.
      Если None/пусто — fallback: следующие 7 дней без воскресенья.
    """
    rows: list[list[InlineKeyboardButton]] = []

    if entries:
        for e in entries:
            for dt in sched_module.future_lesson_datetimes(e["day_of_week"], e["start_time"], n=2):
                label = (
                    f"{DAYS_RU[e['day_of_week']]} {dt.day} {MONTHS_SHORT[dt.month - 1]}"
                    f" · {e['start_time']}"
                )
                rows.append([InlineKeyboardButton(
                    text=label,
                    callback_data=f"hw|cd|{hw_key}|{dt.strftime('%Y%m%d')}",
                )])
    else:
        today = datetime.today().date()
        row: list[InlineKeyboardButton] = []
        for delta in range(7):
            d = today + timedelta(days=delta)
            if d.weekday() == 6:  # воскресенье пропускаем
                continue
            if delta == 0:
                label = f"Сегодня {DAYS_SHORT[d.weekday()]} {d.day}"
            elif delta == 1:
                label = f"Завтра {DAYS_SHORT[d.weekday()]} {d.day}"
            else:
                label = f"{DAYS_SHORT[d.weekday()]} {d.day}"
                if d.month != today.month:
                    label += f" {MONTHS_SHORT[d.month - 1]}"
            row.append(InlineKeyboardButton(
                text=label,
                callback_data=f"hw|cd|{hw_key}|{d.strftime('%Y%m%d')}",
            ))
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

    rows.append([InlineKeyboardButton(text="📆 Без даты", callback_data=f"hw|cd|{hw_key}|none")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_pick_hw_day(entries: list[dict]) -> InlineKeyboardMarkup:
    """
    Личный сценарий: предмет найден в нескольких днях расписания.
    Для каждого слота показываем 2 ближайшие даты.
    Формат callback: hw|pick|{day}|{HH:MM}|{YYYYMMDD}
    """
    rows = []
    for e in entries:
        for dt in sched_module.future_lesson_datetimes(e["day_of_week"], e["start_time"], n=2):
            date_str = f"{dt.day} {MONTHS_SHORT[dt.month - 1]}"
            rows.append([InlineKeyboardButton(
                text=f"{DAYS_RU[e['day_of_week']]} · {e['start_time']}  ({date_str})",
                callback_data=f"hw|pick|{e['day_of_week']}|{e['start_time']}|{dt.strftime('%Y%m%d')}",
            )])
    return InlineKeyboardMarkup(inline_keyboard=rows)
