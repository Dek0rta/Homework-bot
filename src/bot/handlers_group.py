"""
Хендлеры групп и каналов: мониторинг сообщений на предмет ДЗ,
список заданий, настройка предметов, привязка расписания, аналитика.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReactionTypeEmoji,
)

from src.bot import onboarding
from src.bot.keyboards import kb_hw_due_day
from src.bot.utils import delete_after, fmt_due_date, is_chat_admin, safe_delete
from src.core import db
from src.core.constants import DAYS_RU, GROUP_TYPES
from src.services import analytics, llm, prefilter, timetable
from src.services.weeks import parity_suffix

logger = logging.getLogger(__name__)

router = Router()


# ── Фоновый анализ сложности ──────────────────────────────────────────────────

async def _analyze_hw_async(chat_id: int, hw_id: int, subject: str, task: str, due_date: str) -> None:
    """
    Фоновая LLM-оценка времени выполнения ДЗ.
    Не блокирует ответ пользователю — ошибки логируются и игнорируются.
    """
    try:
        est_time = await analytics.estimate_hw_time(subject, task)
        if est_time is not None:
            db.update_hw_estimated_time(hw_id, est_time)
        analytics.update_daily_metrics(chat_id, due_date)
    except Exception:
        logger.exception("Background analytics error for hw_id=%d", hw_id)


# ── Замены уроков ─────────────────────────────────────────────────────────────

async def _try_handle_override(message: Message, text: str, subjects: list[str]) -> bool:
    """
    Пробует записать замену или отмену урока из сообщения.
    True — сообщение обработано как замена, дальше его вести не нужно.
    """
    try:
        result = await llm.detect_schedule_override(text, subjects)
    except Exception:
        logger.exception("Override detection error")
        return False

    if not result:
        return False

    try:
        day = datetime.strptime(result["date"], "%Y-%m-%d").date()
    except (KeyError, TypeError, ValueError):
        return False

    old_subject = (result.get("old_subject") or "").strip()
    new_subject = (result.get("new_subject") or "").strip()
    cancelled   = bool(result.get("cancelled"))

    if not old_subject and not new_subject:
        return False

    # Номер урока: из сообщения либо из расписания по названию предмета
    slot = result.get("slot")
    if not slot and old_subject:
        slot = next(
            (
                lesson["slot"]
                for lesson in timetable.lessons_on(message.chat.id, day)
                if lesson["subject"].strip().lower() == old_subject.lower()
            ),
            None,
        )

    if not slot:
        return False  # непонятно, какой урок менять — не трогаем расписание

    db.save_override(
        message.chat.id,
        day.isoformat(),
        int(slot),
        None if cancelled else (new_subject or None),
        note=f"из сообщения: {text[:80]}",
    )

    try:
        await message.react([ReactionTypeEmoji(emoji="✍️")])
    except Exception:
        pass

    date_label = fmt_due_date(day.isoformat())
    if cancelled:
        body = f"❌ <b>{old_subject or f'{slot} урок'}</b> отменён"
    else:
        body = f"🔄 <b>{slot} урок:</b> {new_subject}"
        if old_subject:
            body += f" <i>(вместо {old_subject})</i>"

    msg = await message.reply(
        f"{body}\n📅 {date_label}\n\n"
        "<i>Учёл в расписании. Отменить — /undo_change</i>",
        parse_mode="HTML",
    )
    asyncio.create_task(delete_after(msg, delay=30))
    return True


@router.message(Command("undo_change"), F.chat.type.in_(GROUP_TYPES))
async def cmd_undo_change(message: Message):
    """Убирает последнюю замену — если бот понял сообщение неправильно."""
    conn = db.get_connection()
    row = conn.execute(
        "SELECT date, slot, subgroup FROM schedule_overrides"
        " WHERE chat_id = ? ORDER BY created_at DESC LIMIT 1",
        (message.chat.id,),
    ).fetchone()
    conn.close()

    if not row:
        await message.reply("Замен пока нет.")
        return

    db.delete_override(message.chat.id, row["date"], row["slot"], row["subgroup"])
    await message.reply(
        f"✅ Замена на {fmt_due_date(row['date'])} убрана — "
        f"{row['slot']} урок вернулся к расписанию."
    )


# ── Детекция ДЗ в сообщениях ──────────────────────────────────────────────────

async def _handle_group_message(message: Message, text: str | None = None, image_path: str | None = None):
    """Проверяем настроенные предметы → детектируем ДЗ через LLM → спрашиваем день сдачи."""
    subjects = db.get_chat_subjects(message.chat.id)
    if not subjects:
        return

    try:
        if image_path:
            result = await llm.detect_group_homework_image(image_path, subjects)
        else:
            # Предфильтр отсекает переписку до платного вызова модели
            if not prefilter.should_analyze(text):
                return

            # Замена урока обсуждается в том же чате — проверяем до ДЗ
            if prefilter.has_override_markers(text):
                if await _try_handle_override(message, text, subjects):
                    return

            result = await llm.detect_group_homework(text, subjects)
    except Exception:
        logger.exception("Group homework detection error")
        return

    if not result:
        return

    subject = result.get("subject", "")
    task    = result.get("task", "")

    # Реакция 👀 — сигнал, что бот увидел ДЗ
    try:
        await message.react([ReactionTypeEmoji(emoji="👀")])
    except Exception:
        pass

    # Ищем уроки с этим предметом в расписании класса
    sched_entries = [
        e for e in db.get_schedule_for_chat(message.chat.id)
        if e["subject"].strip().lower() == subject.strip().lower()
    ]

    # Очередь живёт в БД: рестарт бота между вопросом и нажатием кнопки
    # больше не теряет задание
    pending_id = db.save_pending_homework(message.chat.id, subject, task)

    if sched_entries:
        hint = ""
    elif owner_id:
        hint = "\n\n<i>⚠️ Предмет не найден в расписании — выбери день вручную.</i>"
    else:
        hint = (
            "\n\n<i>⚠️ Расписание не привязано. "
            "Запусти /link_schedule чтобы даты подбирались автоматически.</i>"
        )

    await message.reply(
        "📚 <b>ДЗ найдено</b>\n"
        f"<b>{subject}</b> — {task}\n\n"
        f"📅 На какой день задали?{hint}",
        parse_mode="HTML",
        reply_markup=kb_hw_due_day(pending_id, sched_entries or None),
    )


def _track_member(message: Message) -> None:
    """
    Запоминает автора сообщения как участника чата.
    Каналы не учитываются — там нет from_user.
    """
    if message.from_user and not message.from_user.is_bot:
        try:
            db.remember_chat_member(message.chat.id, message.from_user.id)
        except Exception:
            logger.exception("Не удалось записать членство в чате")


@router.message(F.chat.type.in_(GROUP_TYPES), F.text & ~F.text.startswith("/"))
@router.channel_post(F.text & ~F.text.startswith("/"))
async def handle_group_text(message: Message):
    _track_member(message)

    # Чат в режиме настройки — сообщение может оказаться расписанием
    if await onboarding.try_parse_schedule_text(message):
        return

    await _handle_group_message(message, text=message.text)


@router.message(F.chat.type.in_(GROUP_TYPES), F.photo)
@router.channel_post(F.photo)
async def handle_group_photo(message: Message):
    _track_member(message)

    # Во время настройки фото — это расписание, а не ДЗ
    if await onboarding.try_parse_schedule_photo(message):
        return

    photo = message.photo[-1]
    file  = await message.bot.get_file(photo.file_id)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await message.bot.download_file(file.file_path, tmp_path)
        await _handle_group_message(message, image_path=tmp_path)
    finally:
        os.unlink(tmp_path)


@router.callback_query(F.data.startswith("hw|cd|"))
async def cb_confirm_hw_day(call: CallbackQuery):
    parts      = call.data.split("|")
    pending_id = int(parts[2])
    date_raw   = parts[3]

    pending = db.take_pending_homework(pending_id)
    if not pending:
        await call.answer("Задание уже обработано.", show_alert=True)
        return

    await call.answer()

    if db.chat_homework_exists(pending["chat_id"], pending["subject"], pending["task"]):
        msg = await call.message.edit_text(
            "⚠️ <b>Это ДЗ уже есть в списке</b>\n"
            f"<b>{pending['subject']}</b> — {pending['task']}",
            parse_mode="HTML",
        )
        asyncio.create_task(delete_after(msg))
        return

    if date_raw == "none":
        due_date = None
        due_text = ""
    else:
        d        = datetime.strptime(date_raw, "%Y%m%d")
        due_date = d.strftime("%Y-%m-%d")
        due_text = f"\n📅 Сдать: <b>{fmt_due_date(due_date)}</b>"

    hw_id = db.save_chat_homework(pending["chat_id"], pending["subject"], pending["task"], due_date)

    if due_date:
        asyncio.create_task(_analyze_hw_async(
            pending["chat_id"], hw_id, pending["subject"], pending["task"], due_date,
        ))

    kb_confirm = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📊 Нагрузка класса", callback_data=f"hw|stats|{pending['chat_id']}"),
    ]])

    msg = await call.message.edit_text(
        "📚 <b>ДЗ сохранено</b>\n"
        f"<b>{pending['subject']}</b> — {pending['task']}{due_text}",
        parse_mode="HTML",
        reply_markup=kb_confirm,
    )
    asyncio.create_task(delete_after(msg, delay=20))


# ── Настройка предметов ───────────────────────────────────────────────────────

@router.message(Command("setup_subjects"), F.chat.type.in_(GROUP_TYPES))
@router.channel_post(Command("setup_subjects"))
async def cmd_setup_subjects(message: Message):
    # В каналах from_user=None — постить может только админ канала
    if message.from_user and message.chat.type in GROUP_TYPES:
        if not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
            await message.reply("Только администраторы чата могут настраивать предметы.")
            return

    args = message.text.partition(" ")[2].strip() if message.text else ""
    if not args:
        current = db.get_chat_subjects(message.chat.id)
        if current:
            await message.reply(
                "Текущие предметы:\n" + "\n".join(f"• {s}" for s in current)
                + "\n\nЧтобы изменить: /setup_subjects Математика, Физика, ..."
            )
        else:
            await message.reply(
                "Предметы не настроены.\n"
                "Использование: <code>/setup_subjects Математика, Физика, Химия</code>",
                parse_mode="HTML",
            )
        return

    subjects = [s.strip() for s in args.replace("\n", ",").split(",") if s.strip()]
    db.set_chat_subjects(message.chat.id, subjects)

    if message.from_user:
        db.set_chat_schedule_owner(message.chat.id, message.from_user.id)

    await message.reply(
        "✅ <b>Предметы сохранены</b>\n" + "\n".join(f"• {s}" for s in subjects)
        + "\n\n<i>Твоё расписание будет использоваться для определения дат ДЗ.</i>",
        parse_mode="HTML",
    )


@router.message(Command("link_schedule"), F.chat.type.in_(GROUP_TYPES))
async def cmd_link_schedule(message: Message):
    if not db.has_schedule(message.from_user.id):
        await message.reply(
            "У тебя нет личного расписания.\n"
            "Настрой его в личном чате с ботом командой /schedule."
        )
        return

    db.set_chat_schedule_owner(message.chat.id, message.from_user.id)
    await message.reply(
        f"✅ Расписание <b>{message.from_user.first_name}</b> привязано к группе.\n"
        "Теперь при обнаружении ДЗ бот будет предлагать даты из расписания.",
        parse_mode="HTML",
    )


# ── Список ДЗ ─────────────────────────────────────────────────────────────────

def _build_hw_list(homework: list[dict], group_chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Текст списка и клавиатура с кнопками удаления для /hw."""
    by_subject: dict[str, list] = {}
    for hw in homework:
        by_subject.setdefault(hw["subject"], []).append(hw)

    lines = [f"📚 <b>Домашние задания</b> ({len(homework)})\n"]
    for subject, items in by_subject.items():
        lines.append(f"📌 <b>{subject}</b>")
        for item in items[:10]:
            due = f" → {fmt_due_date(item['due_date'])}" if item.get("due_date") else ""
            lines.append(f"  • {item['task']}{due}  <i>({item['added_at']})</i>")
        lines.append("")

    del_rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            text=f"🗑 {hw['subject'][:15]} — {hw['task'][:25]}",
            callback_data=f"hw|del|{hw['id']}|{group_chat_id}",
        )]
        for hw in homework
    ]
    del_rows.append([InlineKeyboardButton(
        text="🗑 Очистить всё", callback_data=f"hw|clear_all|{group_chat_id}",
    )])
    del_rows.append([InlineKeyboardButton(
        text="📊 Нагрузка класса", callback_data=f"hw|stats|{group_chat_id}",
    )])

    return "\n".join(lines).rstrip(), InlineKeyboardMarkup(inline_keyboard=del_rows)


@router.message(Command("hw"), F.chat.type.in_(GROUP_TYPES))
@router.channel_post(Command("hw"))
async def cmd_hw(message: Message):
    _track_member(message)
    homework = db.get_chat_homework(message.chat.id)

    if not homework:
        subjects = db.get_chat_subjects(message.chat.id)
        msg = await message.reply(
            "Предметы не настроены. Выполни /setup_subjects" if not subjects
            else "ДЗ пока нет — буду отслеживать сообщения!"
        )
        if message.from_user:
            await safe_delete(message)
            asyncio.create_task(delete_after(msg))
        return

    text, kb = _build_hw_list(homework, message.chat.id)

    # Канал — отвечаем прямо в канале (from_user отсутствует)
    if not message.from_user:
        await message.reply(text, parse_mode="HTML", reply_markup=kb)
        return

    # Группа — команду удаляем, список шлём в ЛС чтобы не засорять чат
    await safe_delete(message)
    try:
        await message.bot.send_message(message.from_user.id, text, parse_mode="HTML", reply_markup=kb)
        notify = await message.answer("📬 Список ДЗ отправлен тебе в личные сообщения.")
    except Exception:
        # Бот заблокирован или диалога с пользователем ещё нет
        notify = await message.answer(text, parse_mode="HTML", reply_markup=kb)
    asyncio.create_task(delete_after(notify))


@router.message(Command("today"), F.chat.type.in_(GROUP_TYPES))
async def cmd_today(message: Message):
    """Что сегодня — с учётом чётности недели, подгруппы и замен."""
    _track_member(message)

    if not db.has_class_schedule(message.chat.id):
        await message.reply("Расписание ещё не настроено — /setup")
        return

    subgroup = db.get_user_subgroup(message.chat.id, message.from_user.id) if message.from_user else 0
    await message.reply(
        timetable.format_day(message.chat.id, date.today(), subgroup),
        parse_mode="HTML",
    )


@router.message(Command("tomorrow"), F.chat.type.in_(GROUP_TYPES))
async def cmd_tomorrow(message: Message):
    _track_member(message)

    if not db.has_class_schedule(message.chat.id):
        await message.reply("Расписание ещё не настроено — /setup")
        return

    subgroup = db.get_user_subgroup(message.chat.id, message.from_user.id) if message.from_user else 0
    await message.reply(
        timetable.format_day(message.chat.id, date.today() + timedelta(days=1), subgroup),
        parse_mode="HTML",
    )


@router.message(Command("my_group"), F.chat.type.in_(GROUP_TYPES))
async def cmd_my_group(message: Message):
    """Выбор подгруппы — чтобы видеть только свои уроки."""
    _track_member(message)

    subgroups = db.get_schedule_subgroups(message.chat.id)
    if not subgroups:
        await message.reply("В расписании класса нет деления на подгруппы.")
        return

    current = db.get_user_subgroup(message.chat.id, message.from_user.id)
    rows = [
        [InlineKeyboardButton(
            text=f"{'✅ ' if n == current else ''}{n} группа",
            callback_data=f"grp:{n}",
        )]
        for n in subgroups
    ]
    rows.append([InlineKeyboardButton(
        text=f"{'✅ ' if current == 0 else ''}Показывать все",
        callback_data="grp:0",
    )])

    await message.reply(
        "В какой ты подгруппе?\n"
        "<i>Буду показывать расписание только с твоими уроками.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("grp:"))
async def cb_set_subgroup(call: CallbackQuery):
    subgroup = int(call.data.split(":")[1])
    db.set_user_subgroup(call.message.chat.id, call.from_user.id, subgroup)
    await call.answer("Запомнил" if subgroup else "Показываю все уроки")

    label = f"{subgroup} группа" if subgroup else "все уроки"
    await call.message.edit_text(
        f"✅ {call.from_user.first_name}: {label}\n\n"
        "<i>Расписание в /today и /tomorrow теперь под тебя.</i>",
        parse_mode="HTML",
    )


@router.message(Command("schedule"), F.chat.type.in_(GROUP_TYPES))
@router.channel_post(Command("schedule"))
async def cmd_schedule_group(message: Message):
    """Расписание класса на неделю. Общее для всех — настраивал кто-то один."""
    _track_member(message)
    entries = db.get_class_schedule(message.chat.id)

    if not entries:
        await message.reply(
            "Расписание ещё не настроено.\n"
            "Пришлите фото расписания командой /setup — я распознаю его сам."
        )
        return

    by_day: dict[int, list] = {}
    for e in entries:
        by_day.setdefault(e["day_of_week"], []).append(e)

    lines = ["📅 <b>Расписание класса</b>\n"]
    for day in sorted(by_day):
        lines.append(f"<b>{DAYS_RU[day]}</b>")
        for e in sorted(by_day[day], key=lambda x: (x["slot"], x["subgroup"])):
            line = f"  {e['slot']}. {e['subject']}"
            if e["subgroup"]:
                line += f" · {e['subgroup']} гр."
            line += parity_suffix(e["week_parity"])
            if e["start_time"]:
                line += f"  <i>{e['start_time']}</i>"
            lines.append(line)
        lines.append("")

    footer = []
    if db.get_schedule_subgroups(message.chat.id):
        footer.append("/my_group — выбрать свою подгруппу")
    if db.schedule_has_parity(message.chat.id) and not db.get_parity_anchor(message.chat.id):
        footer.append("⚠️ Не задана текущая неделя — /set_week")

    text = "\n".join(lines).rstrip()
    if footer:
        text += "\n\n" + "\n".join(footer)

    await message.reply(text, parse_mode="HTML")


@router.message(Command("set_week"), F.chat.type.in_(GROUP_TYPES))
async def cmd_set_week(message: Message):
    """Какая неделя сейчас — от этого считается числитель/знаменатель."""
    _track_member(message)

    if not db.schedule_has_parity(message.chat.id):
        await message.reply("В расписании класса нет деления на чётные и нечётные недели.")
        return

    await message.reply(
        "Какая сейчас неделя?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Числитель (нечётная)", callback_data="wk:odd")],
            [InlineKeyboardButton(text="Знаменатель (чётная)", callback_data="wk:even")],
        ]),
    )


@router.callback_query(F.data.startswith("wk:"))
async def cb_set_week(call: CallbackQuery):
    parity = call.data.split(":")[1]

    # Опорная дата — понедельник нечётной недели. Если сейчас чётная,
    # значит нечётной была прошлая.
    this_monday = date.today() - timedelta(days=date.today().weekday())
    anchor = this_monday if parity == "odd" else this_monday - timedelta(days=7)

    db.set_parity_anchor(call.message.chat.id, anchor.isoformat())
    await call.answer("Запомнил")

    label = "числитель" if parity == "odd" else "знаменатель"
    await call.message.edit_text(
        f"✅ Текущая неделя — <b>{label}</b>.\n\n"
        "<i>Дальше чередование считаю сам.</i>",
        parse_mode="HTML",
    )


@router.message(Command("clear_hw"), F.chat.type.in_(GROUP_TYPES))
@router.channel_post(Command("clear_hw"))
async def cmd_clear_hw(message: Message):
    if message.from_user and message.chat.type in GROUP_TYPES:
        if not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
            await message.reply("Только администраторы могут очищать список ДЗ.")
            return

    db.clear_chat_homework(message.chat.id)
    await message.reply("✅ Список ДЗ очищен.")


@router.callback_query(F.data.startswith("hw|del|"))
async def cb_delete_hw(call: CallbackQuery):
    parts         = call.data.split("|")
    hw_id         = int(parts[2])
    group_chat_id = int(parts[3])

    if call.message.chat.type in GROUP_TYPES:
        if not await is_chat_admin(call.bot, call.message.chat.id, call.from_user.id):
            await call.answer("Только администраторы могут удалять ДЗ.", show_alert=True)
            return

    db.delete_chat_homework(hw_id)
    await call.answer("✅ ДЗ удалено")

    homework = db.get_chat_homework(group_chat_id)
    if not homework:
        await call.message.edit_text("📚 Список ДЗ пуст.")
        return

    text, kb = _build_hw_list(homework, group_chat_id)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("hw|clear_all"))
async def cb_hw_clear_all(call: CallbackQuery):
    group_chat_id = int(call.data.split("|")[2])

    if call.message.chat.type in GROUP_TYPES:
        if not await is_chat_admin(call.bot, call.message.chat.id, call.from_user.id):
            await call.answer("Только администраторы могут очищать список ДЗ.", show_alert=True)
            return

    db.clear_chat_homework(group_chat_id)
    await call.answer("✅ Список ДЗ очищен")
    await call.message.edit_text("📚 Список ДЗ очищен.")


# ── Аналитика нагрузки ────────────────────────────────────────────────────────

_CHART_CAPTION = (
    "📊 <b>Нагрузка класса на 2 недели</b>\n\n"
    "🟢 В норме  🟠 Повышенная  🔴 Перегрузка\n"
    "Пунктир — безопасная норма (3 ч/день)"
)


@router.callback_query(F.data.startswith("hw|stats|"))
async def cb_hw_stats(call: CallbackQuery):
    await call.answer()
    chat_id    = int(call.data.split("|")[2])
    chat_title = getattr(call.message.chat, "title", None) or "Класс"
    try:
        img_bytes = analytics.generate_weekly_chart(chat_id, chat_title)
        await call.message.answer_photo(
            BufferedInputFile(img_bytes, filename="load.png"),
            caption=_CHART_CAPTION,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("cb_hw_stats error")
        await call.message.answer("Ошибка генерации графика. Попробуй позже.")


@router.message(Command("stats"), F.chat.type.in_(GROUP_TYPES))
@router.channel_post(Command("stats"))
async def cmd_stats_group(message: Message):
    _track_member(message)
    await safe_delete(message)
    status = await message.answer("📊 Генерирую график нагрузки...")
    try:
        chat_title = getattr(message.chat, "title", None) or "Класс"
        img_bytes  = analytics.generate_weekly_chart(message.chat.id, chat_title)
        await safe_delete(status)
        await message.answer_photo(
            BufferedInputFile(img_bytes, filename="load.png"),
            caption=_CHART_CAPTION,
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Group stats error")
        await status.edit_text("Ошибка генерации графика. Попробуй позже.")


@router.message(Command("export_csv"), F.chat.type.in_(GROUP_TYPES))
@router.channel_post(Command("export_csv"))
async def cmd_export_csv(message: Message):
    if message.from_user and message.chat.type in GROUP_TYPES:
        if not await is_chat_admin(message.bot, message.chat.id, message.from_user.id):
            await message.reply("Только администраторы могут экспортировать данные.")
            return

    await safe_delete(message)
    try:
        csv_bytes = analytics.export_csv(message.chat.id)
        today_str = datetime.today().strftime("%Y%m%d")
        await message.answer_document(
            BufferedInputFile(csv_bytes, filename=f"load_{today_str}.csv"),
            caption=(
                "📊 <b>Экспорт данных о нагрузке</b>\n\n"
                "Колонки: date, task_count, total_time_minutes, total_time_hours, stress_index\n\n"
                "<i>Файл содержит только агрегированные данные класса.\n"
                "Имена учеников и user_id не включены.</i>"
            ),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Export CSV error")
        await message.answer("Ошибка при экспорте данных.")


# ── Справка ───────────────────────────────────────────────────────────────────

@router.message(Command("help"), F.chat.type.in_(GROUP_TYPES))
@router.channel_post(Command("help"))
async def cmd_help_group(message: Message):
    subjects  = db.get_chat_subjects(message.chat.id)
    owner_id  = db.get_chat_schedule_owner(message.chat.id)
    subj_str  = ", ".join(subjects) if subjects else "не настроены"
    owner_str = f"ID {owner_id}" if owner_id else "не привязано"

    await message.reply(
        "📚 <b>Команды (группа / канал)</b>\n\n"
        "/hw — список домашних заданий\n"
        "/stats — график нагрузки класса на 2 недели\n"
        "/export_csv — экспорт метрик нагрузки в CSV <i>(только admin)</i>\n"
        "/setup_subjects — настроить предметы <i>(только admin)</i>\n"
        "/link_schedule — привязать своё расписание <i>(только admin)</i>\n"
        "/clear_hw — очистить список ДЗ <i>(только admin)</i>\n"
        "/help — эта справка\n\n"
        f"<b>Предметы:</b> {subj_str}\n"
        f"<b>Расписание:</b> {owner_str}\n\n"
        "<b>Как работает:</b>\n"
        "• Бот читает каждое сообщение и фото\n"
        "• Если видит ДЗ по известному предмету — спрашивает день\n"
        "• Кнопками можно удалить любое ДЗ из /hw",
        parse_mode="HTML",
    )
