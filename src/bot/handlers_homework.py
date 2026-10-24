"""
Личные домашние задания: прислал — записано.

Ученик кидает что угодно — текст, фото дневника или доски, альбом из
нескольких страниц, скриншот, пересланное из чата класса. Бот находит все
задания, ставит дату сдачи (из сообщения или по расписанию), сохраняет и
показывает карточку. Вопросы — только когда без них никак, всё остальное
правится кнопками под карточкой.

Здесь же обработка кнопок карточек чата класса (префикс gh): логика правки
одна и та же, отличаются только владелец заданий и права на удаление.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.bot import homework_cards as cards
from src.bot import media, onboarding
from src.bot.handlers_reminders import DEFAULT_TIME
from src.bot.utils import is_chat_admin
from src.core import clock, db
from src.core.config import WEB_APP_URL
from src.core.constants import BTN_HOMEWORK, BUTTON_TEXTS
from src.services import analytics
from src.services import homework_intake as intake
from src.services.llm import LLMBadResponse
from src.services.llm_providers import ImageInput, LLMUnavailable

logger = logging.getLogger(__name__)

router = Router()

_albums = media.AlbumCollector()

# Сколько дней назад показывать невыполненные просроченные задания
_OVERDUE_DAYS = 7


# ── Приём сообщений ──────────────────────────────────────────────────────────

@router.message(F.chat.type == "private", F.media_group_id, F.photo | F.document)
async def handle_album(message: Message):
    messages = await _albums.collect(message)
    if messages is None:
        return  # остальные фото альбома обработает первое сообщение

    # Во время настройки альбом — это расписание; берём первое фото
    if await onboarding.try_parse_schedule_photo(messages[0]):
        return

    await process_messages(messages)


@router.message(F.chat.type == "private", F.photo)
async def handle_photo(message: Message):
    # Идёт настройка — фото это расписание, а не домашнее задание
    if await onboarding.try_parse_schedule_photo(message):
        return
    await process_messages([message])


@router.message(F.chat.type == "private", F.document)
async def handle_document(message: Message):
    if media.is_image_document(message):
        await process_messages([message])
        return

    if (message.document.mime_type or "") == "application/pdf":
        await message.reply(
            "PDF пока не читаю. Пришли скриншот или фото нужной страницы — разберу."
        )
        return

    await message.reply("Пришли фото или текст с домашним заданием — разберу и запишу.")


@router.message(
    F.chat.type == "private",
    F.text & ~F.text.startswith("/") & ~F.text.in_(BUTTON_TEXTS),
)
async def handle_text(message: Message, state: FSMContext):
    if await state.get_state() is not None:
        return

    # Идёт настройка — длинный текст это расписание, а не домашнее задание
    if await onboarding.try_parse_schedule_text(message):
        return

    await process_messages([message])


# ── Разбор и сохранение ──────────────────────────────────────────────────────

async def _collect_images(messages: list[Message]) -> tuple[list[ImageInput], int]:
    """Изображения из сообщений и число файлов, которые не удалось прочитать."""
    images: list[ImageInput] = []
    failed = 0
    for message in messages:
        try:
            image = await media.image_from_message(message)
        except media.UnsupportedImage as e:
            logger.info("Не удалось прочитать изображение: %s", e)
            failed += 1
            continue
        if image:
            images.append(image)
    return images, failed


def _save_items(user_id: int, items: list[intake.HomeworkItem]) -> tuple[list[int], int]:
    """Сохраняет задания в личный список. Возвращает (id новых, число дублей)."""
    ids: list[int] = []
    duplicates = 0
    for item in items:
        if db.chat_homework_exists(user_id, item.subject, item.task):
            duplicates += 1
            continue
        ids.append(db.save_chat_homework(
            user_id,
            item.subject,
            item.task,
            item.due_date.isoformat() if item.due_date else None,
            ai_confidence=item.confidence,
            created_by=user_id,
        ))
    return ids, duplicates


async def _estimate_times(rows: list[tuple[int, str, str]]) -> None:
    """Фоновая оценка времени — для вечерних напоминаний «сколько это займёт»."""
    for hw_id, subject, task in rows:
        minutes = await analytics.estimate_hw_time(subject, task)
        if minutes is not None:
            db.update_hw_estimated_time(hw_id, minutes)


async def process_messages(messages: list[Message]) -> None:
    first   = messages[0]
    user_id = first.from_user.id
    text    = "\n".join(t for t in (media.message_text(m) for m in messages) if t)

    images, failed = await _collect_images(messages)
    if not text and not images:
        await first.reply(
            "Не смог открыть это изображение. Пришли его обычным фото, а не файлом."
            if failed else
            "Пришли фото или текст с домашним заданием — разберу и запишу."
        )
        return

    status   = await first.reply("🔍 Разбираю…")
    schedule = intake.schedule_for_user(user_id)
    today    = clock.today()

    try:
        items = await intake.analyze(
            text=text,
            images=images,
            schedule=schedule,
            today=media.reference_day(first, today),
            source="private",
        )
    except LLMUnavailable:
        logger.exception("Модели недоступны при разборе ДЗ")
        db.log_event("homework_parse_failed", user_id=user_id, payload={"reason": "unavailable"})
        await status.edit_text(
            "⚠️ Нейросеть сейчас не отвечает.\n"
            "Перешли мне это сообщение ещё раз через минуту — разберу."
        )
        return
    except LLMBadResponse:
        logger.exception("Не удалось разобрать ответ модели")
        db.log_event("homework_parse_failed", user_id=user_id, payload={"reason": "bad_response"})
        await status.edit_text("⚠️ Не смог разобрать ответ нейросети. Пришли сообщение ещё раз.")
        return

    if not items:
        db.log_event("homework_not_found", user_id=user_id, payload={"images": len(images)})
        await status.edit_text(
            "🤷 Не нашёл здесь домашнего задания.\n\n"
            "Если оно есть — пришли фото чётче или напиши текстом, например:\n"
            "<i>алгебра №245, 247 на пятницу</i>",
            parse_mode="HTML",
        )
        return

    ids, duplicates = _save_items(user_id, items)
    db.log_event("homework_added", user_id=user_id, payload={
        "count": len(ids), "duplicates": duplicates, "images": len(images), "private": True,
    })

    if not ids:
        await status.edit_text(
            "✅ Эти задания уже записаны.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📋 Все ДЗ", callback_data="ph:list"),
            ]]),
        )
        return

    notes: list[str] = []
    if duplicates:
        notes.append(f"<i>Уже были в списке: {duplicates}</i>")
    if failed:
        notes.append(f"<i>Не смог открыть файлов: {failed}</i>")
    if schedule.is_empty:
        notes.append(
            "💡 <i>Пришли фото расписания — /setup — и даты сдачи будут ставиться сами.</i>"
        )

    extra_rows = []
    subscription = db.get_subscription(user_id)
    if not subscription or not subscription["enabled"]:
        extra_rows.append([InlineKeyboardButton(
            text=f"🔔 Напоминать вечером в {DEFAULT_TIME}",
            callback_data=f"ph:remind:{ids[0]}:{ids[-1]}",
        )])

    rows = db.get_homework_range(user_id, ids[0], ids[-1])
    text_out, keyboard = cards.render_card(
        rows, prefix="ph", first_id=ids[0], last_id=ids[-1], today=today,
        notes=notes, extra_rows=extra_rows,
    )
    await status.edit_text(text_out, parse_mode="HTML", reply_markup=keyboard)

    asyncio.create_task(_estimate_times([(r["id"], r["subject"], r["task"]) for r in rows]))


# ── Кнопки карточки (личные и классные) ──────────────────────────────────────

def _owner(call: CallbackQuery, prefix: str) -> int:
    """Чей это список: личный — пользователя, классный — чата карточки."""
    return call.from_user.id if prefix == "ph" else call.message.chat.id


def _schedule_for(prefix: str, owner: int) -> intake.ScheduleSource:
    if prefix == "ph":
        return intake.schedule_for_user(owner)
    return intake.schedule_for_chat(owner)


async def _render_card_in_place(call: CallbackQuery, prefix: str, owner: int, first: int, last: int) -> None:
    rows = db.get_homework_range(owner, first, last)
    text, keyboard = cards.render_card(
        rows, prefix=prefix, first_id=first, last_id=last, today=clock.today(),
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^(ph|gh):(due|set|del|card):"))
async def cb_card(call: CallbackQuery):
    parts          = call.data.split(":")
    prefix, action = parts[0], parts[1]
    owner          = _owner(call, prefix)
    first, last    = cards.parse_span(parts)

    if action == "card":
        await call.answer()
        await _render_card_in_place(call, prefix, owner, first, last)
        return

    hw_id = int(parts[2])
    row   = db.get_homework(hw_id)
    # Кнопка правит только задания своего списка — чужой id из подделанного
    # callback_data сюда не пройдёт
    if not row or row["chat_id"] != owner:
        await call.answer("Это задание уже удалено.", show_alert=True)
        await _render_card_in_place(call, prefix, owner, first, last)
        return

    today = clock.today()

    if action == "due":
        await call.answer()
        lessons = _schedule_for(prefix, owner).next_lessons(row["subject"], today, n=3)
        text, keyboard = cards.render_due_picker(
            row, prefix=prefix, first_id=first, last_id=last, lesson_dates=lessons, today=today,
        )
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        return

    if action == "set":
        raw = parts[3]
        due = None if raw == "0" else f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        db.set_homework_due(hw_id, due)
        db.log_event("homework_due_changed", chat_id=None if prefix == "ph" else owner,
                     user_id=call.from_user.id)
        await call.answer("Дата сохранена")
        await _render_card_in_place(call, prefix, owner, first, last)
        return

    if action == "del":
        if prefix == "gh" and not await is_chat_admin(call.bot, owner, call.from_user.id):
            await call.answer("Удалять задания класса могут только администраторы.", show_alert=True)
            return
        db.delete_chat_homework(hw_id)
        db.log_event("homework_deleted", chat_id=None if prefix == "ph" else owner,
                     user_id=call.from_user.id)
        await call.answer("Удалено")
        await _render_card_in_place(call, prefix, owner, first, last)


@router.callback_query(F.data.startswith("ph:undo:"))
async def cb_undo_all(call: CallbackQuery):
    first, last = cards.parse_span(call.data.split(":"))
    deleted = db.delete_homework_range(call.from_user.id, first, last)
    db.log_event("homework_undone", user_id=call.from_user.id, payload={"count": deleted})
    await call.answer("Отменено")
    await call.message.edit_text("↩️ Отменил — ничего не записано.")


@router.callback_query(F.data.startswith("ph:remind:"))
async def cb_enable_reminders(call: CallbackQuery):
    user_id = call.from_user.id
    chats   = db.get_chats_for_user(user_id)
    # Класс, если он известен: напоминание покажет и его уроки на завтра
    db.subscribe_reminders(user_id, chats[0] if chats else user_id, DEFAULT_TIME)
    db.log_event("reminder_subscribed", user_id=user_id, payload={"from": "card"})
    await call.answer(f"Буду напоминать в {DEFAULT_TIME}. Время — /reminders")

    first, last = cards.parse_span(call.data.split(":"))
    await _render_card_in_place(call, "ph", user_id, first, last)


# ── Список заданий ───────────────────────────────────────────────────────────

def _list_view(user_id: int):
    today = clock.today()
    since = (today - timedelta(days=_OVERDUE_DAYS)).isoformat()
    chats = [user_id] + [c for c in db.get_chats_for_user(user_id) if c != user_id]
    rows  = db.get_upcoming_homework(chats, user_id, since)
    return cards.render_list(rows, own_chat_id=user_id, today=today, web_app_url=WEB_APP_URL)


@router.message(Command("hw"), F.chat.type == "private")
@router.message(F.text == BTN_HOMEWORK, F.chat.type == "private")
async def cmd_my_homework(message: Message):
    text, keyboard = _list_view(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "ph:list")
async def cb_list(call: CallbackQuery):
    await call.answer()
    text, keyboard = _list_view(call.from_user.id)
    await call.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("ph:done:"))
async def cb_toggle_done(call: CallbackQuery):
    user_id = call.from_user.id
    hw_id   = int(call.data.split(":")[2])
    row     = db.get_homework(hw_id)

    allowed = {user_id, *db.get_chats_for_user(user_id)}
    if not row or row["chat_id"] not in allowed:
        await call.answer("Это задание уже удалено.", show_alert=True)
    else:
        done = not db.is_homework_done(user_id, hw_id)
        db.set_homework_done(user_id, hw_id, done)
        await call.answer("Отмечено ✅" if done else "Вернул в список")

    text, keyboard = _list_view(user_id)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
