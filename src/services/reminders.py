"""
Вечерние напоминания о завтрашних заданиях.

Зачем: без них бот полностью пассивен — он ждёт, пока о нём вспомнят.
Но если ученик вспомнил про домашку сам, бот ему уже не нужен. Причина
открыть его завтра появляется только тогда, когда он пишет первым.

Ограничение Telegram: бот не может написать пользователю, который не
открывал с ним личный чат. Поэтому подписка — явное действие, а не
настройка по умолчанию.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from src.core import db
from src.services import timetable

logger = logging.getLogger(__name__)

# Как часто проверять, кому пора отправлять
TICK_SECONDS = 60

# Норма нагрузки — выше неё помечаем день как тяжёлый
HEAVY_DAY_MINUTES = 180


def _plural_tasks(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "задание"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "задания"
    return "заданий"


def _format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"~{minutes} мин"
    hours = minutes / 60
    return f"~{hours:.0f} ч" if hours == int(hours) else f"~{hours:.1f} ч"


def build_reminder(chat_id: int, user_id: int, target: date) -> str | None:
    """
    Текст напоминания о заданиях на дату target.
    None — если напоминать не о чем: так пользователь не получает пустых
    сообщений и не отписывается из-за шума.
    """
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT h.id, h.subject, h.task, h.estimated_time_minutes,"
            "       COALESCE(s.is_done, 0) AS is_done"
            "  FROM chat_homework h"
            "  LEFT JOIN user_homework_status s"
            "    ON s.homework_id = h.id AND s.user_id = ?"
            " WHERE h.chat_id = ? AND h.due_date = ?"
            " ORDER BY h.id",
            (user_id, chat_id, target.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    pending = [r for r in rows if not r["is_done"]]
    if not pending:
        return None

    total_minutes = sum(r["estimated_time_minutes"] or 30 for r in pending)

    lines = [
        f"🌙 <b>На завтра: {len(pending)} {_plural_tasks(len(pending))}</b>"
        f"  ·  {_format_duration(total_minutes)}\n"
    ]

    for row in pending:
        task = row["task"]
        if len(task) > 70:
            task = task[:67] + "…"
        lines.append(f"📌 <b>{row['subject']}</b> — {task}")

    if total_minutes > HEAVY_DAY_MINUTES:
        lines.append("\n⚠️ <i>День загруженный — лучше начать сегодня.</i>")

    # Что завтра по расписанию — полезно рядом со списком заданий
    subgroup = db.get_user_subgroup(chat_id, user_id)
    lessons  = timetable.lessons_on(chat_id, target, subgroup)
    if lessons:
        names = [l["subject"] for l in lessons if not l["is_cancelled"]]
        if names:
            lines.append(f"\n📅 <i>Уроки: {', '.join(names[:8])}</i>")

    lines.append("\n<i>Отключить — /reminders_off</i>")
    return "\n".join(lines)


async def send_due_reminders(bot) -> int:
    """
    Отправляет напоминания тем, кому пора. Возвращает число отправленных.
    Вызывается планировщиком раз в минуту.
    """
    now      = datetime.now()
    now_hhmm = now.strftime("%H:%M")
    today    = now.date().isoformat()
    tomorrow = now.date() + timedelta(days=1)

    sent = 0
    for sub in db.due_subscriptions(now_hhmm, today):
        user_id = sub["user_id"]
        chat_id = sub["chat_id"]

        try:
            text = build_reminder(chat_id, user_id, tomorrow)

            # Помечаем отправленным в любом случае: иначе пустой день
            # заставит планировщик пересчитывать его каждую минуту до полуночи.
            db.mark_reminder_sent(user_id, today)

            if text is None:
                continue

            await bot.send_message(user_id, text, parse_mode="HTML")
            db.log_event("reminder_sent", chat_id=chat_id, user_id=user_id)
            sent += 1

        except Exception as exc:
            # Пользователь заблокировал бота — отписываем, чтобы не долбиться
            if "blocked" in str(exc).lower() or "chat not found" in str(exc).lower():
                db.unsubscribe_reminders(user_id)
                db.log_event("reminder_blocked", chat_id=chat_id, user_id=user_id)
                logger.info("Пользователь %s заблокировал бота — отписан", user_id)
            else:
                logger.exception("Ошибка отправки напоминания user_id=%s", user_id)

    return sent


async def scheduler_loop(bot) -> None:
    """Фоновый цикл проверки напоминаний. Живёт всё время работы бота."""
    logger.info("Планировщик напоминаний запущен")
    while True:
        try:
            count = await send_due_reminders(bot)
            if count:
                logger.info("Отправлено напоминаний: %d", count)
        except Exception:
            logger.exception("Ошибка в планировщике напоминаний")

        await asyncio.sleep(TICK_SECONDS)
