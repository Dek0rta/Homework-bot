"""
Сборка расписания на конкретный день.

Постоянная сетка — только основа. Что реально будет на уроках, зависит
от трёх вещей, и все они накладываются здесь:

  1. чётность недели  — числитель/знаменатель
  2. подгруппа ученика — английский 1 группа против 2 группы
  3. замены на дату    — «вместо физики будет история», «химию отменили»

Порядок применения важен: сначала отбираем уроки постоянной сетки, затем
поверх кладём замены. Замена всегда сильнее расписания.
"""

from __future__ import annotations

from datetime import date

from src.core import db
from src.core.constants import LESSON_TIMES
from src.services.weeks import lesson_happens_on, parity_suffix


def _parse_anchor(chat_id: int) -> date | None:
    raw = db.get_parity_anchor(chat_id)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def lessons_on(chat_id: int, day: date, subgroup: int = 0) -> list[dict]:
    """
    Уроки класса на конкретную дату — то, что реально будет.

    subgroup: 0 — показать всё, включая обе подгруппы;
              n — только общие уроки и уроки подгруппы n.

    Возвращает список уроков, отсортированных по номеру, где каждый содержит:
      slot, subject, start_time, subgroup, week_parity,
      is_override (была ли замена), is_cancelled (урок отменён), note
    """
    anchor = _parse_anchor(chat_id)

    # Постоянная сетка на этот день недели
    grid = [
        lesson for lesson in db.get_class_schedule(chat_id, subgroup or None)
        if lesson["day_of_week"] == day.weekday()
        and lesson_happens_on(lesson["week_parity"], day, anchor)
    ]

    # Чётность входит в ключ: без заданной опорной даты в одном слоте
    # законно оказываются оба варианта урока, и они не должны затирать
    # друг друга.
    result: dict[tuple[int, int, str], dict] = {}
    for lesson in grid:
        key = (lesson["slot"], lesson["subgroup"], lesson["week_parity"])
        result[key] = {
            "slot":         lesson["slot"],
            "subject":      lesson["subject"],
            "start_time":   lesson["start_time"],
            "subgroup":     lesson["subgroup"],
            "week_parity":  lesson["week_parity"],
            "is_override":  False,
            "is_cancelled": False,
            "note":         None,
        }

    # Замены поверх сетки — они всегда важнее постоянного расписания
    for override in db.get_overrides(chat_id, day.isoformat()):
        slot     = override["slot"]
        ov_group = override["subgroup"]

        if subgroup and ov_group not in (0, subgroup):
            continue  # замена для чужой подгруппы

        # Замена для всего класса перекрывает уроки всех подгрупп в этом слоте
        affected = [
            key for key in result
            if key[0] == slot and (ov_group == 0 or key[1] == ov_group)
        ]
        if not affected:
            # Замена на слот, которого нет в постоянной сетке — добавляем урок
            affected = [(slot, ov_group, "")]

        for key in affected:
            existing = result.get(key, {})
            result[key] = {
                "slot":         slot,
                "subject":      override["subject"] or existing.get("subject", ""),
                "start_time":   LESSON_TIMES[slot - 1] if 1 <= slot <= len(LESSON_TIMES) else "",
                "subgroup":     key[1],
                "week_parity":  existing.get("week_parity", ""),
                "is_override":  True,
                "is_cancelled": override["subject"] is None,
                "note":         override["note"],
            }

    return sorted(result.values(), key=lambda x: (x["slot"], x["subgroup"], x["week_parity"]))


def format_day(chat_id: int, day: date, subgroup: int = 0) -> str:
    """Расписание на день в виде готового текста для Telegram."""
    from src.core.constants import DAYS_RU, MONTHS_SHORT

    lessons = lessons_on(chat_id, day, subgroup)
    header  = f"<b>{DAYS_RU[day.weekday()]}, {day.day} {MONTHS_SHORT[day.month - 1]}</b>"

    if not lessons:
        return f"{header}\n\nУроков нет."

    lines = [header, ""]
    for lesson in lessons:
        line = f"{lesson['slot']}. "

        if lesson["is_cancelled"]:
            line += f"<s>{lesson['subject']}</s> — отменён"
        else:
            line += lesson["subject"]
            if lesson["is_override"]:
                line += " 🔄"

        if lesson["subgroup"]:
            line += f" · {lesson['subgroup']} группа"

        line += parity_suffix(lesson["week_parity"])

        if lesson["start_time"] and not lesson["is_cancelled"]:
            line += f"  <i>{lesson['start_time']}</i>"

        lines.append(line)

        if lesson["note"]:
            lines.append(f"   <i>{lesson['note']}</i>")

    return "\n".join(lines)


def subjects_for_detection(chat_id: int) -> list[str]:
    """
    Предметы для распознавания ДЗ — все из расписания, независимо от
    подгруппы и чётности: ДЗ могут задать по любому из них.
    """
    return db.get_class_subjects(chat_id)
