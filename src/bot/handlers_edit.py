"""
Точечная правка расписания.

После распознавания фото модель обычно ошибается в одном-двух предметах из
тридцати. Раньше единственным выходом было переснять всё заново — это
раздражает сильнее, чем сама ошибка. Здесь можно поправить конкретную клетку.

Навигация: день → урок → действие. Меню редактирования живёт одним
сообщением, которое перерисовывается на каждом шаге, чтобы не засорять чат.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.bot.utils import is_chat_admin, safe_delete
from src.core import db
from src.core.constants import DAYS_RU, DAYS_SHORT, GROUP_TYPES, LESSON_TIMES
from src.services.weeks import parity_suffix

logger = logging.getLogger(__name__)

router = Router()


class EditSchedule(StatesGroup):
    entering_subject = State()


# ── Клавиатуры ───────────────────────────────────────────────────────────────

def _kb_days(chat_id: int) -> InlineKeyboardMarkup:
    """Дни недели с числом уроков — сразу видно, где пусто."""
    schedule = db.get_class_schedule(chat_id)
    per_day: dict[int, int] = {}
    for lesson in schedule:
        per_day[lesson["day_of_week"]] = per_day.get(lesson["day_of_week"], 0) + 1

    buttons = [
        InlineKeyboardButton(
            text=f"{DAYS_SHORT[day]} ({per_day.get(day, 0)})",
            callback_data=f"ed:day:{day}",
        )
        for day in range(6)  # понедельник–суббота
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(text="✖️ Закрыть", callback_data="ed:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _day_lessons(chat_id: int, day: int) -> list[dict]:
    return sorted(
        (l for l in db.get_class_schedule(chat_id) if l["day_of_week"] == day),
        key=lambda x: (x["slot"], x["subgroup"], x["week_parity"]),
    )


def _kb_day(chat_id: int, day: int) -> InlineKeyboardMarkup:
    """Уроки дня: занятые слоты правим, свободные заполняем."""
    lessons  = _day_lessons(chat_id, day)
    by_slot: dict[int, list[dict]] = {}
    for lesson in lessons:
        by_slot.setdefault(lesson["slot"], []).append(lesson)

    rows = []
    for slot in range(1, 9):
        items = by_slot.get(slot, [])
        if items:
            for lesson in items:
                label = f"{slot}. {lesson['subject']}"
                if lesson["subgroup"]:
                    label += f" · {lesson['subgroup']}гр"
                label += parity_suffix(lesson["week_parity"])
                rows.append([InlineKeyboardButton(
                    text=label[:60],
                    callback_data=f"ed:pick:{day}:{slot}:{lesson['subgroup']}:{lesson['week_parity'] or '-'}",
                )])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{slot}. — пусто ({LESSON_TIMES[slot - 1]})",
                callback_data=f"ed:new:{day}:{slot}",
            )])

    rows.append([InlineKeyboardButton(text="◀️ К дням", callback_data="ed:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _kb_lesson_actions(day: int, slot: int, subgroup: int, parity: str) -> InlineKeyboardMarkup:
    suffix = f"{day}:{slot}:{subgroup}:{parity or '-'}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"ed:rename:{suffix}")],
        [InlineKeyboardButton(text="🗑 Удалить урок",  callback_data=f"ed:del:{suffix}")],
        [InlineKeyboardButton(text="◀️ Назад",          callback_data=f"ed:day:{day}")],
    ])


# ── Вход в редактор ──────────────────────────────────────────────────────────

@router.message(Command("edit"), F.chat.type.in_(GROUP_TYPES))
async def cmd_edit(message: Message):
    if not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
        await message.reply("Править расписание может администратор чата.")
        return

    if not db.has_class_schedule(message.chat.id):
        await message.reply("Расписание ещё не настроено — /setup")
        return

    await message.reply(
        "✏️ <b>Правка расписания</b>\n\nВыбери день:",
        parse_mode="HTML",
        reply_markup=_kb_days(message.chat.id),
    )


@router.callback_query(F.data == "ed:back")
async def cb_back_to_days(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "✏️ <b>Правка расписания</b>\n\nВыбери день:",
        parse_mode="HTML",
        reply_markup=_kb_days(call.message.chat.id),
    )


@router.callback_query(F.data == "ed:close")
async def cb_close(call: CallbackQuery):
    await call.answer()
    await safe_delete(call.message)


@router.callback_query(F.data.startswith("ed:day:"))
async def cb_open_day(call: CallbackQuery):
    await call.answer()
    day = int(call.data.split(":")[2])
    await call.message.edit_text(
        f"✏️ <b>{DAYS_RU[day]}</b>\n\nНажми на урок, чтобы изменить:",
        parse_mode="HTML",
        reply_markup=_kb_day(call.message.chat.id, day),
    )


@router.callback_query(F.data.startswith("ed:pick:"))
async def cb_pick_lesson(call: CallbackQuery):
    await call.answer()
    _, _, day, slot, subgroup, parity = call.data.split(":")
    parity = "" if parity == "-" else parity

    lesson = next(
        (
            l for l in _day_lessons(call.message.chat.id, int(day))
            if l["slot"] == int(slot)
            and l["subgroup"] == int(subgroup)
            and (l["week_parity"] or "") == parity
        ),
        None,
    )
    if not lesson:
        await call.answer("Урок уже изменён", show_alert=True)
        return

    details = f"<b>{lesson['subject']}</b>"
    if lesson["subgroup"]:
        details += f" · {lesson['subgroup']} группа"
    details += parity_suffix(lesson["week_parity"])

    await call.message.edit_text(
        f"{DAYS_RU[int(day)]}, {slot} урок\n{details}\n\nЧто сделать?",
        parse_mode="HTML",
        reply_markup=_kb_lesson_actions(int(day), int(slot), int(subgroup), parity),
    )


# ── Действия над уроком ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ed:del:"))
async def cb_delete_lesson(call: CallbackQuery):
    _, _, day, slot, subgroup, parity = call.data.split(":")
    parity = "" if parity == "-" else parity

    conn = db.get_connection()
    conn.execute(
        "DELETE FROM class_schedule"
        " WHERE chat_id=? AND day_of_week=? AND slot=? AND subgroup=? AND week_parity=?",
        (call.message.chat.id, int(day), int(slot), int(subgroup), parity),
    )
    conn.commit()
    conn.close()

    db.log_event("schedule_edited", chat_id=call.message.chat.id,
                 user_id=call.from_user.id, payload={"action": "delete"})

    await call.answer("Урок удалён")
    await call.message.edit_text(
        f"✏️ <b>{DAYS_RU[int(day)]}</b>\n\nНажми на урок, чтобы изменить:",
        parse_mode="HTML",
        reply_markup=_kb_day(call.message.chat.id, int(day)),
    )


@router.callback_query(F.data.startswith("ed:rename:"))
@router.callback_query(F.data.startswith("ed:new:"))
async def cb_ask_subject(call: CallbackQuery, state: FSMContext):
    await call.answer()
    parts = call.data.split(":")
    action = parts[1]

    if action == "new":
        day, slot, subgroup, parity = int(parts[2]), int(parts[3]), 0, ""
        prompt = f"{DAYS_RU[day]}, {slot} урок\n\nНапиши название предмета:"
    else:
        day, slot, subgroup = int(parts[2]), int(parts[3]), int(parts[4])
        parity = "" if parts[5] == "-" else parts[5]
        prompt = f"{DAYS_RU[day]}, {slot} урок\n\nНапиши новое название:"

    await state.set_state(EditSchedule.entering_subject)
    await state.update_data(
        day=day, slot=slot, subgroup=subgroup, parity=parity,
        msg_id=call.message.message_id, chat_id=call.message.chat.id,
    )

    await call.message.edit_text(
        prompt + "\n\n<i>Для подгруппы добавь «1 гр» или «2 гр».</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"ed:day:{day}"),
        ]]),
    )


def _extract_subgroup(text: str) -> tuple[str, int]:
    """
    Вытаскивает номер подгруппы из названия: «Английский 1 гр» → («Английский», 1).
    Позволяет задать подгруппу, не добавляя отдельный экран.
    """
    import re

    match = re.search(r"\s*(\d)\s*(?:гр\.?|группа|подгруппа)\s*$", text, re.IGNORECASE)
    if not match:
        return text.strip(), 0
    return text[:match.start()].strip(), int(match.group(1))


@router.message(EditSchedule.entering_subject, F.chat.type.in_(GROUP_TYPES))
async def handle_subject_input(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await safe_delete(message)

    subject, parsed_group = _extract_subgroup(message.text or "")
    if not subject:
        return

    day      = data["day"]
    slot     = data["slot"]
    subgroup = parsed_group or data["subgroup"]
    parity   = data["parity"]
    chat_id  = data["chat_id"]

    conn = db.get_connection()
    # Старая запись могла отличаться подгруппой — удаляем её адресно
    conn.execute(
        "DELETE FROM class_schedule"
        " WHERE chat_id=? AND day_of_week=? AND slot=? AND subgroup=? AND week_parity=?",
        (chat_id, day, slot, data["subgroup"], parity),
    )
    conn.execute(
        "INSERT OR REPLACE INTO class_schedule"
        " (chat_id, day_of_week, slot, subject, subgroup, week_parity)"
        " VALUES (?,?,?,?,?,?)",
        (chat_id, day, slot, subject, subgroup, parity),
    )
    conn.commit()
    conn.close()

    # Предметы для детекции ДЗ пересобираем — иначе новый предмет не распознается
    subjects = db.get_class_subjects(chat_id)
    if subjects:
        db.set_chat_subjects(chat_id, subjects)

    db.log_event("schedule_edited", chat_id=chat_id, user_id=message.from_user.id,
                 payload={"action": "rename"})

    try:
        await message.bot.edit_message_text(
            chat_id=chat_id,
            message_id=data["msg_id"],
            text=f"✏️ <b>{DAYS_RU[day]}</b>\n\nНажми на урок, чтобы изменить:",
            parse_mode="HTML",
            reply_markup=_kb_day(chat_id, day),
        )
    except Exception:
        await message.answer(
            f"✅ Сохранено: {slot} урок — {subject}",
            reply_markup=_kb_day(chat_id, day),
        )
