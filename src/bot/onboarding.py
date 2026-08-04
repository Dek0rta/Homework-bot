"""
Быстрый старт класса.

Задача — довести чат от «бота только что добавили» до рабочего состояния
за один шаг. Ручной ввод расписания по клеткам занимает под сотню действий,
поэтому основной путь здесь — фото расписания: класс присылает снимок из
дневника или со стены, модель распознаёт его целиком, человек только
подтверждает.

Предметы для детекции ДЗ выводятся из распознанного расписания, так что
отдельный /setup_subjects больше не нужен.
"""

from __future__ import annotations

import logging
import os
import tempfile

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.bot.utils import is_chat_admin
from src.core import db
from src.core.constants import DAYS_RU, GROUP_TYPES
from src.services import llm

logger = logging.getLogger(__name__)

router = Router()

# Ниже этого порога уверенности просим переснять, а не показываем разбор
MIN_CONFIDENCE = 0.35

# Чаты, ожидающие фото расписания. chat_id → инициатор (или None для «любого»)
_awaiting_schedule: dict[int, int | None] = {}


def is_awaiting_schedule(chat_id: int) -> bool:
    return chat_id in _awaiting_schedule


def start_awaiting(chat_id: int, user_id: int | None = None) -> None:
    _awaiting_schedule[chat_id] = user_id


def stop_awaiting(chat_id: int) -> None:
    _awaiting_schedule.pop(chat_id, None)


# ── Тексты ────────────────────────────────────────────────────────────────────

WELCOME = (
    "👋 <b>Привет! Я веду домашние задания класса.</b>\n\n"
    "Чтобы начать, пришлите <b>фото расписания</b> — из дневника, со стены "
    "или скриншот. Я распознаю его сам.\n\n"
    "Можно и текстом, если так удобнее.\n\n"
    "<i>Дальше я буду замечать домашние задания в переписке "
    "и собирать их в один список.</i>"
)

NOT_RECOGNIZED = (
    "Не смог разобрать расписание на этом фото.\n\n"
    "Обычно помогает: снять ровно, без бликов, чтобы все дни попали в кадр.\n"
    "Либо пришлите расписание текстом."
)


def _format_preview(lessons: list[dict]) -> str:
    """Распознанное расписание по дням — для проверки человеком."""
    by_day: dict[int, list] = {}
    for lesson in lessons:
        by_day.setdefault(lesson["day"], []).append(lesson)

    lines = [f"📅 <b>Распознал расписание</b> — {len(lessons)} урок(ов)\n"]
    for day in sorted(by_day):
        lines.append(f"<b>{DAYS_RU[day]}</b>")
        for lesson in sorted(by_day[day], key=lambda x: x["slot"]):
            lines.append(f"  {lesson['slot']}. {lesson['subject']}")
        lines.append("")

    lines.append("Всё верно?")
    return "\n".join(lines)


def _kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, сохранить", callback_data="onb:save")],
        [InlineKeyboardButton(text="🔄 Прислать другое фото", callback_data="onb:retry")],
    ])


# ── Бота добавили в группу ───────────────────────────────────────────────────

@router.my_chat_member()
async def on_added_to_chat(event: ChatMemberUpdated):
    """Приветствие сразу после добавления в группу — без команд со стороны людей."""
    if event.chat.type not in GROUP_TYPES:
        return

    was_present = event.old_chat_member.status in ("member", "administrator", "creator")
    is_present  = event.new_chat_member.status in ("member", "administrator", "creator")
    if was_present or not is_present:
        return

    if db.has_class_schedule(event.chat.id):
        return  # чат уже настроен — например, бота вернули после удаления

    db.log_event("bot_added", chat_id=event.chat.id)
    start_awaiting(event.chat.id)
    await event.bot.send_message(event.chat.id, WELCOME, parse_mode="HTML")


# ── Ручной запуск настройки ──────────────────────────────────────────────────

@router.message(Command("setup"), F.chat.type.in_(GROUP_TYPES))
async def cmd_setup(message: Message):
    if not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
        # Не админ — не мешаем, просто объясняем
        await message.reply("Настроить расписание может администратор чата.")
        return

    start_awaiting(message.chat.id, message.from_user.id)
    await message.reply(
        "📸 Пришлите фото расписания — или отправьте его текстом.",
        parse_mode="HTML",
    )


# ── Приём расписания ─────────────────────────────────────────────────────────

async def try_parse_schedule_photo(message: Message) -> bool:
    """
    Пробует прочитать расписание с фото. True — фото обработано как расписание.
    Вызывается из группового хендлера до детекции ДЗ.
    """
    if not is_awaiting_schedule(message.chat.id):
        return False

    status = await message.reply("Читаю расписание...")

    photo = message.photo[-1]
    file  = await message.bot.get_file(photo.file_id)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await message.bot.download_file(file.file_path, tmp_path)
        result = await llm.parse_schedule_image(tmp_path)
    except Exception:
        logger.exception("Ошибка распознавания расписания")
        await status.edit_text("Не получилось прочитать фото. Попробуйте ещё раз.")
        return True
    finally:
        os.unlink(tmp_path)

    await _handle_parsed(status, message.chat.id, result)
    return True


async def try_parse_schedule_text(message: Message) -> bool:
    """Разбор расписания из текстового сообщения. True — сообщение обработано."""
    if not is_awaiting_schedule(message.chat.id):
        return False

    text = message.text or ""
    if len(text) < 20:
        return False  # слишком коротко для расписания — пусть идёт обычным путём

    status = await message.reply("Разбираю расписание...")
    try:
        result = await llm.parse_schedule_text(text)
    except Exception:
        logger.exception("Ошибка разбора расписания из текста")
        await status.edit_text("Не получилось разобрать. Пришлите фото расписания.")
        return True

    await _handle_parsed(status, message.chat.id, result)
    return True


# Распознанное, но ещё не подтверждённое расписание. chat_id → уроки
_pending_schedule: dict[int, list[dict]] = {}


async def _handle_parsed(status: Message, chat_id: int, result: dict) -> None:
    lessons    = result.get("lessons", [])
    confidence = result.get("confidence", 0.0)

    if not lessons or confidence < MIN_CONFIDENCE:
        db.log_event("schedule_failed", chat_id=chat_id,
                     payload={"confidence": round(confidence, 2)})
        await status.edit_text(NOT_RECOGNIZED, parse_mode="HTML")
        return

    db.log_event("schedule_recognized", chat_id=chat_id,
                 payload={"lessons": len(lessons), "confidence": round(confidence, 2)})
    _pending_schedule[chat_id] = lessons
    await status.edit_text(
        _format_preview(lessons),
        parse_mode="HTML",
        reply_markup=_kb_confirm(),
    )


@router.callback_query(F.data == "onb:save")
async def cb_save_schedule(call: CallbackQuery):
    chat_id = call.message.chat.id
    lessons = _pending_schedule.pop(chat_id, None)

    if not lessons:
        await call.answer("Расписание уже сохранено или устарело.", show_alert=True)
        return

    await call.answer()

    count = db.save_class_schedule(chat_id, lessons)
    db.log_event("schedule_saved", chat_id=chat_id, user_id=call.from_user.id,
                 payload={"lessons": count})

    # Предметы для детекции ДЗ выводим из расписания — отдельная настройка не нужна
    subjects = db.get_class_subjects(chat_id)
    if subjects:
        db.set_chat_subjects(chat_id, subjects)

    stop_awaiting(chat_id)

    await call.message.edit_text(
        f"✅ <b>Готово!</b> Расписание сохранено — {count} урок(ов).\n\n"
        f"Предметы подхватил из расписания: {', '.join(subjects[:8])}"
        + ("…" if len(subjects) > 8 else "")
        + "\n\n"
        "Теперь просто пишите домашние задания в чат — я замечу их сам "
        "и соберу в список.\n\n"
        "📋 /hw — список заданий\n"
        "📅 /schedule — посмотреть расписание\n"
        "📊 /stats — нагрузка класса",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "onb:retry")
async def cb_retry(call: CallbackQuery):
    await call.answer()
    _pending_schedule.pop(call.message.chat.id, None)
    db.log_event("schedule_retry", chat_id=call.message.chat.id)
    start_awaiting(call.message.chat.id)
    await call.message.edit_text("📸 Хорошо, пришлите другое фото расписания.")
