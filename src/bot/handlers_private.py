"""
Хендлеры личного чата: редактор расписания, Google Calendar, разбор ДЗ,
график нагрузки и справка.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from src.bot import onboarding
from src.bot.backup import make_backup_json, save_backup
from src.bot.keyboards import (
    MAIN_KB,
    kb_days,
    kb_lessons,
    kb_pick_hw_day,
    temp_get_subject,
    temp_set_subject,
)
from src.bot.states import CalendarAuth, HomeworkConfirm, ScheduleSetup
from src.bot.utils import safe_delete
from src.core import db
from src.core.constants import (
    BTN_CALENDAR,
    BTN_SCHEDULE,
    BTN_SET_SCHEDULE,
    BTN_STATS,
    BUTTON_TEXTS,
    DAYS_RU,
    LESSON_TIMES,
    time_key,
)
from src.services import analytics
from src.services import calendar as calendar_api
from src.services import llm
from src.services import schedule as sched_module

logger = logging.getLogger(__name__)

router = Router()

# Незавершённые OAuth-флоу Google, по user_id
_auth_flows: dict[int, object] = {}


# ── /start, /cancel, /help ────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message):
    await safe_delete(message)
    await message.answer(
        f"Привет, <b>{message.from_user.first_name}</b>! "
        "Я добавляю домашние задания прямо в Google Calendar.\n\n"
        "<b>Быстрый старт:</b>\n"
        "1. <b>📸 Пришли фото расписания</b> — распознаю сам\n"
        "2. <b>🔗 Google Calendar</b> — подключи аккаунт\n"
        "3. Отправь фото тетради или текст с ДЗ — готово!\n\n"
        "<b>Команды:</b>\n"
        "/setup — расписание по фото\n"
        "/schedule — вписать расписание вручную\n"
        "/my_schedule — посмотреть расписание\n"
        "/auth — подключить Google Calendar\n"
        "/stats — график нагрузки класса",
        parse_mode="HTML",
        reply_markup=MAIN_KB,
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await safe_delete(message)
    await state.clear()
    await message.answer("Отменено.", reply_markup=MAIN_KB)


@router.message(Command("help"), F.chat.type == "private")
async def cmd_help_private(message: Message):
    await message.answer(
        "📱 <b>Команды (личный чат)</b>\n\n"
        "/start — главное меню\n"
        "/schedule — редактор расписания по дням\n"
        "/my_schedule — посмотреть своё расписание\n"
        "/auth — подключить Google Calendar\n"
        "/stats — график нагрузки класса\n"
        "/backup — резервная копия расписания\n"
        "/cancel — отменить текущее действие\n\n"
        "<b>Как пользоваться:</b>\n"
        "1. Настрой расписание — /schedule\n"
        "2. Подключи Google Calendar — /auth\n"
        "3. Отправь фото ДЗ или текст — бот сам добавит\n\n"
        "<b>В группе/канале:</b>\n"
        "Добавь бота, выдай права администратора,\n"
        "затем выполни /setup_subjects — /help покажет подробности.",
        parse_mode="HTML",
        reply_markup=MAIN_KB,
    )


# ── /backup ───────────────────────────────────────────────────────────────────

@router.message(Command("backup"), F.chat.type == "private")
async def cmd_backup(message: Message):
    backup_json = make_backup_json()
    data        = json.loads(backup_json)
    n_lessons   = len(data.get("schedule", []))
    n_subj      = len(data.get("chat_subjects", []))

    if not n_lessons and not n_subj:
        await message.answer(
            "База данных пуста.\n"
            "Сначала настрой расписание, потом используй /backup для сохранения.",
            reply_markup=MAIN_KB,
        )
        return

    text = (
        f"💾 <b>Резервная копия</b>  ({n_lessons} уроков)\n\n"
        "Скопируй строку ниже и сохрани как переменную окружения\n"
        f"<code>SCHEDULE_BACKUP</code>:\n\n"
        f"<code>{backup_json}</code>"
    )

    if len(text) <= 4096:
        await message.answer(text, parse_mode="HTML", reply_markup=MAIN_KB)
    else:
        await message.answer_document(
            BufferedInputFile(backup_json.encode(), filename="schedule_backup.json"),
            caption=(
                f"💾 Резервная копия ({n_lessons} уроков). "
                "Сохрани как переменную SCHEDULE_BACKUP."
            ),
            reply_markup=MAIN_KB,
        )


# ── Редактор расписания ───────────────────────────────────────────────────────

async def open_schedule_editor(message: Message, state: FSMContext):
    existing = db.get_schedule(message.from_user.id)

    # Конвертируем DB-записи в temp-формат, сопоставляя время со слотами
    temp: dict[str, dict] = {}
    for e in existing:
        day_key = str(e["day_of_week"])
        try:
            slot = LESSON_TIMES.index(e["start_time"])
        except ValueError:
            # Нестандартное время — занимаем первый свободный слот дня
            day_slots = temp.get(day_key, {})
            slot = next((s for s in range(8) if str(s) not in day_slots), None)
            if slot is None:
                continue
        temp_set_subject(temp, int(day_key), slot, e["subject"])

    await state.set_state(ScheduleSetup.choosing_day)
    await state.update_data(temp=temp)

    # Пустышка с ReplyKeyboardRemove, сразу удаляется — убирает нижнюю клавиатуру без мусора
    tmp = await message.answer(".", reply_markup=ReplyKeyboardRemove())
    await safe_delete(tmp)
    await message.answer("📆 Расписание:", reply_markup=kb_days(temp))


@router.message(F.text == BTN_SET_SCHEDULE, F.chat.type == "private")
async def btn_set_schedule(message: Message, state: FSMContext):
    """
    Кнопка расписания предлагает фото первым: ручной ввод — это до сотни
    нажатий, и большинство до конца не доходит.
    """
    await safe_delete(message)
    onboarding.start_awaiting(message.chat.id, message.from_user.id)
    await message.answer(
        "📸 <b>Пришли фото расписания</b>\n\n"
        "Из дневника, со стены или скриншотом — распознаю сам.\n"
        "Можно и текстом.\n\n"
        "<i>Вписать по клеткам вручную — /schedule</i>",
        parse_mode="HTML",
    )


@router.message(Command("schedule"), F.chat.type == "private")
async def cmd_schedule_manual(message: Message, state: FSMContext):
    """Ручной редактор по клеткам — запасной путь, если фото не читается."""
    await safe_delete(message)
    onboarding.stop_awaiting(message.chat.id)
    try:
        await open_schedule_editor(message, state)
    except Exception as e:
        logger.exception("Ошибка в open_schedule_editor")
        await message.answer(f"⚠️ Ошибка: {e}", reply_markup=MAIN_KB)


@router.callback_query(F.data.startswith("sched:day:"))
async def cb_select_day(call: CallbackQuery, state: FSMContext):
    await call.answer()
    day  = int(call.data.split(":")[2])
    data = await state.get_data()
    temp = data["temp"]

    await call.message.edit_text(
        f"📚 <b>{DAYS_RU[day]}</b>\n\n"
        "Нажми на урок чтобы задать или изменить предмет.\n"
        "Нажми ещё раз — чтобы очистить.",
        parse_mode="HTML",
        reply_markup=kb_lessons(day, temp),
    )


@router.callback_query(F.data == "sched:back")
async def cb_back_to_days(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await state.set_state(ScheduleSetup.choosing_day)
    await call.message.edit_text("📆 Расписание:", reply_markup=kb_days(data["temp"]))


@router.callback_query(F.data.startswith("sched:slot:"))
async def cb_select_slot(call: CallbackQuery, state: FSMContext):
    await call.answer()
    _, _, day_str, slot_str = call.data.split(":")
    day, slot = int(day_str), int(slot_str)
    data      = await state.get_data()
    temp      = data["temp"]
    subject   = temp_get_subject(temp, day, slot)
    time      = LESSON_TIMES[slot]

    await state.set_state(ScheduleSetup.entering_lesson_name)
    await state.update_data(editing_day=day, editing_slot=slot, sched_msg_id=call.message.message_id)

    if subject:
        text = (
            f"<b>{slot + 1} урок</b> · {time}\n"
            f"Сейчас: <b>{subject}</b>\n\n"
            "Напиши новое название или отправь <code>-</code> чтобы очистить:"
        )
    else:
        text = (
            f"<b>{slot + 1} урок</b> · {time}\n\n"
            "Напиши название предмета (например: Математика, Классный час, Физ-ра):"
        )

    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"sched:day:{day}")
        ]]),
    )


@router.message(ScheduleSetup.entering_lesson_name, ~F.text.in_(BUTTON_TEXTS))
async def handle_lesson_name(message: Message, state: FSMContext):
    await safe_delete(message)
    data = await state.get_data()
    day  = data.get("editing_day")
    slot = data.get("editing_slot")
    temp = data.get("temp", {})

    # Состояние зависло без данных (например после перезапуска) — сбрасываем
    if day is None or slot is None:
        await state.clear()
        await open_schedule_editor(message, state)
        return

    text = message.text.strip()
    temp_set_subject(temp, day, slot, "" if text == "-" else text)

    await state.update_data(temp=temp)
    await state.set_state(ScheduleSetup.choosing_day)

    sched_msg_id = data.get("sched_msg_id")
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=sched_msg_id,
            text=f"📚 <b>{DAYS_RU[day]}</b>",
            parse_mode="HTML",
            reply_markup=kb_lessons(day, temp),
        )
    except Exception:
        await message.answer(
            f"📚 <b>{DAYS_RU[day]}</b>",
            parse_mode="HTML",
            reply_markup=kb_lessons(day, temp),
        )


@router.callback_query(F.data == "sched:save")
async def cb_save_schedule(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    temp = data.get("temp", {})

    entries = [
        {"day": int(day_str), "subject": subject, "start_time": LESSON_TIMES[int(slot_str)]}
        for day_str, slots in temp.items()
        for slot_str, subject in slots.items()
        if subject
    ]

    if not entries:
        await call.answer("Расписание пустое — добавь хотя бы один урок!", show_alert=True)
        return

    db.save_schedule(call.from_user.id, entries)
    await state.clear()
    asyncio.create_task(save_backup(call.bot))

    by_day: dict[int, list] = {}
    for e in entries:
        by_day.setdefault(e["day"], []).append(e)

    lines = [f"✅ <b>Расписание сохранено</b> — {len(entries)} урок(ов)\n"]
    for day_idx in sorted(by_day):
        lines.append(f"<b>{DAYS_RU[day_idx]}</b>")
        for e in sorted(by_day[day_idx], key=lambda x: time_key(x["start_time"])):
            slot   = LESSON_TIMES.index(e["start_time"]) if e["start_time"] in LESSON_TIMES else -1
            prefix = f"{slot + 1} ур." if slot >= 0 else ""
            lines.append(f"  {prefix} {e['start_time']} — {e['subject']}")
        lines.append("")

    await safe_delete(call.message)
    await call.message.answer("\n".join(lines).rstrip(), parse_mode="HTML", reply_markup=MAIN_KB)


@router.message(Command("my_schedule"))
@router.message(F.text == BTN_SCHEDULE)
async def btn_my_schedule(message: Message):
    await safe_delete(message)
    schedule = db.get_schedule(message.from_user.id)
    if not schedule:
        await message.answer(
            "Расписание ещё не настроено.\nНажми <b>✏️ Изменить расписание</b>.",
            parse_mode="HTML",
            reply_markup=MAIN_KB,
        )
        return

    by_day: dict[int, list] = {}
    for e in schedule:
        by_day.setdefault(e["day_of_week"], []).append(e)

    lines = ["<b>📅 Расписание</b>\n"]
    for day_idx in sorted(by_day):
        lines.append(f"<b>{DAYS_RU[day_idx]}</b>")
        for e in sorted(by_day[day_idx], key=lambda x: time_key(x["start_time"])):
            try:
                slot_num = LESSON_TIMES.index(e["start_time"]) + 1
                lines.append(f"  {slot_num} ур. {e['start_time']} — {e['subject']}")
            except ValueError:
                lines.append(f"  {e['start_time']} — {e['subject']}")
        lines.append("")

    await message.answer("\n".join(lines).rstrip(), parse_mode="HTML", reply_markup=MAIN_KB)


# ── Google Calendar ───────────────────────────────────────────────────────────

@router.message(Command("auth"))
@router.message(F.text == BTN_CALENDAR)
async def btn_calendar(message: Message, state: FSMContext):
    await safe_delete(message)
    if calendar_api.is_connected(message.from_user.id):
        await message.answer(
            "Google Calendar уже подключён к твоему аккаунту.\n"
            "Отвязать — /disconnect_calendar",
            reply_markup=MAIN_KB,
        )
        return

    if not calendar_api.credentials_file_exists():
        await message.answer(
            "Файл <code>data/credentials.json</code> не найден.\n\n"
            "Как получить:\n"
            "1. Google Cloud Console → APIs &amp; Services\n"
            "2. Enable → Google Calendar API\n"
            "3. Credentials → Create → OAuth 2.0 → Desktop app\n"
            "4. Download JSON → переименуй в <code>credentials.json</code>\n"
            "5. Положи в папку <code>data/</code>",
            parse_mode="HTML",
            reply_markup=MAIN_KB,
        )
        return

    auth_url, flow = calendar_api.get_auth_url()
    _auth_flows[message.from_user.id] = flow

    await state.set_state(CalendarAuth.waiting_for_code)
    await message.answer(
        "1. Перейди по ссылке и разреши доступ:\n"
        f"<code>{auth_url}</code>\n\n"
        "2. Скопируй полученный код и отправь его сюда.\n\n"
        "<i>ДЗ будут добавляться в твой личный календарь.</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("disconnect_calendar"), F.chat.type == "private")
async def cmd_disconnect_calendar(message: Message):
    await safe_delete(message)
    if not calendar_api.is_connected(message.from_user.id):
        await message.answer("Google Calendar и так не подключён.", reply_markup=MAIN_KB)
        return

    calendar_api.disconnect(message.from_user.id)
    await message.answer(
        "✅ Google Calendar отвязан.\n"
        "Уже созданные события останутся в календаре — удали их вручную, если нужно.",
        reply_markup=MAIN_KB,
    )


@router.message(CalendarAuth.waiting_for_code)
async def handle_auth_code(message: Message, state: FSMContext):
    flow = _auth_flows.pop(message.from_user.id, None)
    if not flow:
        await message.answer(
            "Сессия авторизации истекла. Нажми 🔗 Google Calendar снова.",
            reply_markup=MAIN_KB,
        )
        await state.clear()
        return

    try:
        calendar_api.exchange_code(message.from_user.id, flow, message.text.strip())
        await state.clear()
        await message.answer(
            "Google Calendar подключён! Теперь можешь отправлять ДЗ.",
            reply_markup=MAIN_KB,
        )
    except Exception as e:
        logger.exception("Auth error")
        await message.answer(f"Ошибка авторизации: {e}\n\nПопробуй снова.", reply_markup=MAIN_KB)
        await state.clear()


# ── Разбор ДЗ и добавление в календарь ────────────────────────────────────────

def _find_subject_days(subject: str, schedule: list[dict]) -> list[dict]:
    """Все уроки расписания с совпадающим предметом (без учёта регистра)."""
    s = subject.strip().lower()
    return [e for e in schedule if e["subject"].strip().lower() == s]


async def _do_add_to_calendar(status: Message, parsed: dict, user_id: int):
    """Добавляет ДЗ в календарь пользователя и редактирует статусное сообщение."""
    subject  = parsed.get("subject", "Неизвестно")
    task     = parsed.get("task", "")
    day      = parsed.get("due_lesson_day")
    time_str = parsed.get("due_lesson_time")

    if day is None or not time_str:
        await status.edit_text(
            f"Предмет: <b>{subject}</b>\n"
            f"Задание: {task}\n\n"
            "Не смог определить ближайший урок. Проверь расписание.",
            parse_mode="HTML",
        )
        return

    # Пользователь выбрал конкретную дату — используем её, иначе ближайший урок
    if "lesson_dt_iso" in parsed:
        lesson_dt = datetime.fromisoformat(parsed["lesson_dt_iso"])
    else:
        lesson_dt = sched_module.next_lesson_datetime(day, time_str)

    try:
        event_link = await calendar_api.add_homework_event(user_id, subject, task, lesson_dt)
    except RuntimeError as e:
        if "not_authorized" in str(e):
            await status.edit_text(
                f"Предмет: <b>{subject}</b>\n"
                f"Задание: {task}\n\n"
                "Google Calendar не подключён к твоему аккаунту.\n"
                "Нажми 🔗 Google Calendar или выполни /auth.",
                parse_mode="HTML",
            )
        else:
            await status.edit_text(f"Ошибка Calendar: {e}")
        return
    except Exception as e:
        logger.exception("Calendar error")
        await status.edit_text(f"Ошибка при добавлении в Calendar: {e}")
        return

    kb_rows = []
    if event_link:
        kb_rows.append([InlineKeyboardButton(text="📅 Открыть в календаре", url=event_link)])
    kb_rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main:menu")])

    await status.edit_text(
        "✅ <b>Добавлено в Google Calendar!</b>\n\n"
        f"📚 <b>Предмет:</b> {subject}\n"
        f"📝 <b>Задание:</b> {task}\n"
        f"📅 <b>Урок:</b> {DAYS_RU[day]}, {lesson_dt.strftime('%d.%m')} в {time_str}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )


@router.callback_query(F.data == "main:menu")
async def cb_main_menu(call: CallbackQuery):
    await call.answer()
    await safe_delete(call.message)
    await call.bot.send_message(call.message.chat.id, "Главное меню", reply_markup=MAIN_KB)


async def _apply_parsed(
    status: Message,
    parsed: dict,
    state: FSMContext,
    schedule: list[dict],
    user_id: int,
):
    """Сверяет предмет с расписанием и либо добавляет ДЗ, либо просит уточнить день."""
    subject  = parsed.get("subject", "Неизвестно")
    task     = parsed.get("task", "")
    matching = _find_subject_days(subject, schedule)

    if not matching:
        await status.edit_text(
            f"Предмет <b>{subject}</b> не найден в расписании.\n"
            "Проверь расписание командой /my_schedule.",
            parse_mode="HTML",
        )
        return

    if len(matching) > 1:
        await state.set_state(HomeworkConfirm.choosing_day)
        await state.update_data(pending_parsed=parsed)
        await status.edit_text(
            f"📚 <b>{subject}</b>\n"
            f"📝 {task}\n\n"
            "Этот предмет есть в нескольких днях — выбери нужный урок:",
            parse_mode="HTML",
            reply_markup=kb_pick_hw_day(matching),
        )
        return

    # Ровно одно совпадение — день/время берём из расписания, а не из ответа LLM
    parsed["due_lesson_day"]  = matching[0]["day_of_week"]
    parsed["due_lesson_time"] = matching[0]["start_time"]
    await _do_add_to_calendar(status, parsed, user_id)


@router.callback_query(HomeworkConfirm.choosing_day, F.data.startswith("hw|pick|"))
async def cb_pick_hw_day(call: CallbackQuery, state: FSMContext):
    await call.answer()
    # формат: hw|pick|{day}|{HH:MM}|{YYYYMMDD}
    _, _, day_str, time_str, date_raw = call.data.split("|")
    lesson_dt = datetime.combine(
        datetime.strptime(date_raw, "%Y%m%d").date(),
        datetime.strptime(time_str, "%H:%M").time(),
    )

    data   = await state.get_data()
    parsed = data.get("pending_parsed", {})
    parsed["due_lesson_day"]  = int(day_str)
    parsed["due_lesson_time"] = time_str
    parsed["lesson_dt_iso"]   = lesson_dt.isoformat()

    await state.clear()
    await safe_delete(call.message)
    status = await call.bot.send_message(call.message.chat.id, "Добавляю в Calendar...")
    await _do_add_to_calendar(status, parsed, call.from_user.id)


async def process_homework(message: Message, text: str, state: FSMContext):
    await safe_delete(message)

    if not db.has_schedule(message.from_user.id):
        await message.answer(
            "Сначала нужно расписание.\n\n"
            "📸 Пришли его фото — распознаю сам: /setup\n"
            "✏️ Или впиши вручную: /schedule",
            reply_markup=MAIN_KB,
        )
        return

    schedule = db.get_schedule(message.from_user.id)
    status   = await message.answer("Анализирую задание...")

    try:
        parsed = await llm.parse_homework_text(text, schedule)
    except Exception as e:
        logger.exception("LLM error")
        await status.edit_text(f"Ошибка при анализе текста: {e}")
        return

    await _apply_parsed(status, parsed, state, schedule, message.from_user.id)


@router.message(F.chat.type == "private", F.photo)
async def handle_photo(message: Message, state: FSMContext):
    # Идёт настройка — фото это расписание, а не домашнее задание
    if await onboarding.try_parse_schedule_photo(message):
        return

    await safe_delete(message)

    if not db.has_schedule(message.from_user.id):
        await message.answer(
            "Сначала нужно расписание.\n\n"
            "📸 Пришли его фото — распознаю сам: /setup\n"
            "✏️ Или впиши вручную: /schedule",
            reply_markup=MAIN_KB,
        )
        return

    status = await message.answer("Читаю фото...")
    photo  = message.photo[-1]
    file   = await message.bot.get_file(photo.file_id)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await message.bot.download_file(file.file_path, tmp_path)
        schedule = db.get_schedule(message.from_user.id)

        try:
            parsed = await llm.parse_homework_image(tmp_path, schedule)
        except Exception as e:
            logger.exception("LLM image error")
            await status.edit_text(f"Ошибка при анализе фото: {e}")
            return

        await _apply_parsed(status, parsed, state, schedule, message.from_user.id)
    finally:
        os.unlink(tmp_path)


@router.message(F.chat.type == "private", F.text & ~F.text.startswith("/") & ~F.text.in_(BUTTON_TEXTS))
async def handle_text(message: Message, state: FSMContext):
    if await state.get_state() is not None:
        return

    # Идёт настройка — длинный текст это расписание, а не домашнее задание
    if await onboarding.try_parse_schedule_text(message):
        return

    await process_homework(message, message.text, state)


# ── График нагрузки ───────────────────────────────────────────────────────────

@router.message(Command("stats"), F.chat.type == "private")
@router.message(F.text == BTN_STATS, F.chat.type == "private")
async def cmd_stats_private(message: Message):
    await safe_delete(message)

    # Только чаты, к которым причастен сам пользователь. Раньше был фолбэк
    # «любая группа с данными» — ученик одного класса видел график другого.
    group_ids = db.get_chats_for_user(message.from_user.id)

    if not group_ids:
        await message.answer(
            "📊 <b>Нагрузка класса</b>\n\n"
            "Не вижу, к какому классу ты относишься.\n\n"
            "Бот должен быть добавлен в чат класса, а там выполнено "
            "/setup_subjects. Если чат уже настроен — отметь любое задание "
            "выполненным в приложении, и график станет доступен.",
            parse_mode="HTML",
            reply_markup=MAIN_KB,
        )
        return

    status = await message.answer("📊 Генерирую график нагрузки...")
    try:
        img_bytes = analytics.generate_weekly_chart(group_ids[0], "Класс")
        await safe_delete(status)
        await message.answer_photo(
            BufferedInputFile(img_bytes, filename="load.png"),
            caption=(
                "📊 <b>Нагрузка класса на 2 недели</b>\n\n"
                "🟢 В норме  🟠 Повышенная  🔴 Перегрузка\n"
                "Пунктир — безопасная норма (3 ч/день)\n\n"
                "<i>Данные анонимизированы — имена учеников не сохраняются.</i>"
            ),
            parse_mode="HTML",
            reply_markup=MAIN_KB,
        )
    except Exception:
        logger.exception("Private stats error")
        await status.edit_text("Ошибка генерации графика. Попробуй позже.")
