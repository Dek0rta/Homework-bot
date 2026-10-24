"""
Карточки домашних заданий: что записано, выбор даты, список на неделю.

Карточка строится из строк БД, а не из состояния в памяти: после рестарта
бота кнопки старой карточки продолжают работать. В callback_data лежит
только префикс, действие и id — диапазон id описывает пачку заданий,
распознанных из одного сообщения.

Префиксы: ph — личный чат, gh — чат класса.
"""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from src.core.constants import DAYS_SHORT, MONTHS_SHORT
from src.services.homework_intake import LOW_CONFIDENCE

# Сколько заданий показывать в списке, остальное — в приложении
LIST_LIMIT = 30


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return few
    return many


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def date_label(d: date | None, today: date) -> str:
    """«завтра, пт 31 окт» / «пн, 3 ноя» / «без даты»."""
    if d is None:
        return "без даты"
    base = f"{DAYS_SHORT[d.weekday()].lower()}, {d.day} {MONTHS_SHORT[d.month - 1]}"
    if d == today:
        return "сегодня, " + base
    if d == today + timedelta(days=1):
        return "завтра, " + base
    return base


def short_date(d: date | None) -> str:
    """«пн 27.10» — для кнопок."""
    if d is None:
        return "без даты"
    return f"{DAYS_SHORT[d.weekday()].lower()} {d.day:02d}.{d.month:02d}"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ── Карточка распознанной пачки ──────────────────────────────────────────────

def render_card(
    rows: list[dict],
    *,
    prefix: str,
    first_id: int,
    last_id: int,
    today: date,
    notes: list[str] | None = None,
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """
    Текст и кнопки карточки. rows — задания пачки из БД
    (id, subject, task, due_date, ai_confidence).
    """
    if not rows:
        return "🗑 Задания удалены.", None

    n     = len(rows)
    title = "Записал" if prefix == "ph" else "Записал в список класса"
    lines = [f"✅ <b>{title}: {n} {plural(n, 'задание', 'задания', 'заданий')}</b>", ""]

    for row in rows:
        due = _parse_iso(row.get("due_date"))
        lines.append(f"📚 <b>{escape(row['subject'])}</b> — {escape(row['task'])}")
        lines.append(f"      📅 {date_label(due, today)}")
        confidence = row.get("ai_confidence")
        if confidence is not None and confidence < LOW_CONFIDENCE:
            lines.append("      ⚠️ <i>мог прочитать неточно — проверь</i>")

    for note in notes or []:
        lines += ["", note]

    span = f"{first_id}:{last_id}"
    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        due = _parse_iso(row.get("due_date"))
        keyboard.append([
            InlineKeyboardButton(
                text=f"📅 {_cut(row['subject'], 16)} · {short_date(due)}",
                callback_data=f"{prefix}:due:{row['id']}:{span}",
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"{prefix}:del:{row['id']}:{span}"),
        ])

    if prefix == "ph":
        keyboard.append([
            InlineKeyboardButton(text="↩️ Отменить всё", callback_data=f"ph:undo:{span}"),
            InlineKeyboardButton(text="📋 Все ДЗ", callback_data="ph:list"),
        ])

    keyboard += extra_rows or []
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)


# ── Выбор даты ───────────────────────────────────────────────────────────────

def due_options(lesson_dates: list[date], today: date, days: int = 7) -> list[tuple[date, bool]]:
    """
    Варианты даты: ближайшие уроки предмета плюс ближайшие дни без воскресений.
    Возвращает (дата, это_урок_предмета) по возрастанию.
    """
    options: dict[date, bool] = {d: True for d in lesson_dates}
    for offset in range(1, days + 1):
        d = today + timedelta(days=offset)
        if d.weekday() != 6:
            options.setdefault(d, False)
    return sorted(options.items())


def render_due_picker(
    row: dict,
    *,
    prefix: str,
    first_id: int,
    last_id: int,
    lesson_dates: list[date],
    today: date,
) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        f"📅 <b>Когда сдавать?</b>\n\n"
        f"<b>{escape(row['subject'])}</b> — {escape(_cut(row['task'], 120))}\n\n"
        "<i>📚 — дни, когда по расписанию есть этот урок</i>"
    )
    span    = f"{first_id}:{last_id}"
    buttons = [
        InlineKeyboardButton(
            text=("📚 " if is_lesson else "") + short_date(d),
            callback_data=f"{prefix}:set:{row['id']}:{d.strftime('%Y%m%d')}:{span}",
        )
        for d, is_lesson in due_options(lesson_dates, today)
    ]
    keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    keyboard.append([
        InlineKeyboardButton(text="📆 Без даты", callback_data=f"{prefix}:set:{row['id']}:0:{span}"),
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"{prefix}:card:{span}"),
    ])
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


# ── Список заданий ───────────────────────────────────────────────────────────

def render_list(
    rows: list[dict],
    *,
    own_chat_id: int,
    today: date,
    web_app_url: str = "",
) -> tuple[str, InlineKeyboardMarkup | None]:
    """
    Список заданий по датам с личными отметками. rows — из
    db.get_upcoming_homework, включая просроченные за последние дни.
    Выполненные просроченные не показываются: о них уже можно забыть.
    """
    visible = [
        r for r in rows
        if not (r["is_done"] and (_parse_iso(r["due_date"]) or today) < today)
    ]

    if not visible:
        text = (
            "📋 <b>Домашних заданий нет</b>\n\n"
            "Пришли фото или текст с ДЗ — запишу и поставлю дату сдачи."
        )
        return text, _app_keyboard(web_app_url)

    hidden  = max(0, len(visible) - LIST_LIMIT)
    visible = visible[:LIST_LIMIT]

    lines = ["📋 <b>Домашние задания</b>"]
    current_header = None
    for number, row in enumerate(visible, 1):
        due = _parse_iso(row["due_date"])
        if due is not None and due < today:
            header = "⏰ Просрочено"
        elif due is None:
            header = "Без даты"
        else:
            header = date_label(due, today).capitalize()

        if header != current_header:
            lines += ["", f"<b>{header}</b>"]
            current_header = header

        mark  = "✅" if row["is_done"] else "▫️"
        body  = f"<b>{escape(row['subject'])}</b> — {escape(_cut(row['task'], 90))}"
        if row["is_done"]:
            body = f"<s>{body}</s>"
        shared = "" if row["chat_id"] == own_chat_id else " 👥"
        lines.append(f"{number}. {mark} {body}{shared}")

    if hidden:
        lines += ["", f"<i>…и ещё {hidden} — в приложении</i>"]
    lines += ["", "<i>👥 — из чата класса. Нажми номер, чтобы отметить выполненным.</i>"]

    toggles = [
        InlineKeyboardButton(
            text=("↩️ " if row["is_done"] else "✅ ") + str(number),
            callback_data=f"ph:done:{row['id']}",
        )
        for number, row in enumerate(visible, 1)
    ]
    keyboard = [toggles[i:i + 5] for i in range(0, len(toggles), 5)]
    app = _app_keyboard(web_app_url)
    if app:
        keyboard += app.inline_keyboard
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)


def _app_keyboard(web_app_url: str) -> InlineKeyboardMarkup | None:
    if not web_app_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌐 Открыть приложение", web_app=WebAppInfo(url=web_app_url)),
    ]])


def parse_span(parts: list[str]) -> tuple[int, int]:
    """Последние два элемента callback_data — первый и последний id пачки."""
    return int(parts[-2]), int(parts[-1])
