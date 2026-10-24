"""
Разбор присланного домашнего задания: от сообщения до готовых записей.

Модель только читает: какие задания, по каким предметам, указан ли срок.
Всё, что можно проверить, проверяет код:

  • предмет сводится к названию из расписания («англ. яз» → «Английский язык»);
  • дата сдачи — явная из сообщения, если она правдоподобна, иначе следующий
    урок по расписанию. Ученик не должен выбирать день на каждое задание,
    если ответ очевиден из расписания.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Sequence

from src.core import db
from src.services import llm, timetable
from src.services.llm_providers import ImageInput

# Ниже этой уверенности задание помечается «проверь»
LOW_CONFIDENCE = 0.6

# Насколько далеко вперёд ищем следующий урок предмета
_LOOKAHEAD_DAYS = 21

# Явная дата дальше этого срока — скорее ошибка распознавания
_MAX_DUE_DAYS = 120

DueSource = Literal["explicit", "schedule", "none"]


@dataclass
class HomeworkItem:
    subject: str
    task: str
    due_date: date | None
    due_source: DueSource
    confidence: float
    in_schedule: bool

    @property
    def needs_check(self) -> bool:
        return self.confidence < LOW_CONFIDENCE


# ── Источники расписания ─────────────────────────────────────────────────────

class ScheduleSource:
    """Откуда брать предметы и даты уроков. Базовый вариант — расписания нет."""

    def subjects(self) -> list[str]:
        return []

    def next_lessons(self, subject: str, after: date, n: int = 3) -> list[date]:
        return []

    def next_lesson(self, subject: str, after: date) -> date | None:
        lessons = self.next_lessons(subject, after, n=1)
        return lessons[0] if lessons else None

    @property
    def is_empty(self) -> bool:
        return not self.subjects()


class PersonalSchedule(ScheduleSource):
    """Личное расписание из таблицы schedule: дни недели без замен и чётности."""

    def __init__(self, entries: list[dict]):
        self._entries = entries

    @classmethod
    def for_user(cls, user_id: int) -> "PersonalSchedule":
        return cls(db.get_schedule(user_id))

    def subjects(self) -> list[str]:
        return sorted({e["subject"] for e in self._entries})

    def next_lessons(self, subject: str, after: date, n: int = 3) -> list[date]:
        key  = _norm(subject)
        days = {e["day_of_week"] for e in self._entries if _norm(e["subject"]) == key}
        if not days:
            return []
        result = []
        for offset in range(1, _LOOKAHEAD_DAYS + 1):
            d = after + timedelta(days=offset)
            if d.weekday() in days:
                result.append(d)
                if len(result) == n:
                    break
        return result


class ClassSchedule(ScheduleSource):
    """
    Расписание класса: учитывает чётность недель, подгруппу и замены,
    поэтому отменённый урок не станет датой сдачи.
    """

    def __init__(self, chat_id: int, subgroup: int = 0):
        self._chat_id  = chat_id
        self._subgroup = subgroup

    def subjects(self) -> list[str]:
        return timetable.subjects_for_detection(self._chat_id)

    def next_lessons(self, subject: str, after: date, n: int = 3) -> list[date]:
        key    = _norm(subject)
        result = []
        for offset in range(1, _LOOKAHEAD_DAYS + 1):
            d = after + timedelta(days=offset)
            lessons = timetable.lessons_on(self._chat_id, d, self._subgroup)
            if any(_norm(l["subject"]) == key and not l["is_cancelled"] for l in lessons):
                result.append(d)
                if len(result) == n:
                    break
        return result


def schedule_for_user(user_id: int) -> ScheduleSource:
    """
    Расписание для личных ДЗ: своё, если настроено, иначе расписание класса,
    в чате которого пользователь состоит.
    """
    if db.has_schedule(user_id):
        return PersonalSchedule.for_user(user_id)

    for chat_id in db.get_chats_for_user(user_id):
        if db.has_class_schedule(chat_id):
            return ClassSchedule(chat_id, db.get_user_subgroup(chat_id, user_id))

    return ScheduleSource()


def schedule_for_chat(chat_id: int) -> ScheduleSource:
    """Расписание группового чата: общее расписание класса или личное владельца."""
    if db.has_class_schedule(chat_id):
        return ClassSchedule(chat_id)

    owner_id = db.get_chat_schedule_owner(chat_id)
    if owner_id and db.has_schedule(owner_id):
        return PersonalSchedule.for_user(owner_id)

    return ScheduleSource()


# ── Предметы ─────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Ключ сравнения: регистр, ё/е, пунктуация и пробелы не важны."""
    text = (text or "").casefold().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", "", text)


def _is_abbreviation(short: str, full: str) -> bool:
    """
    «литра» → «литература», «физра» → «физкультура», «англяз» → «английскийязык»:
    начало совпадает, а остальные буквы идут в том же порядке.
    """
    if len(short) < 3 or not full.startswith(short[:3]):
        return False
    it = iter(full)
    return all(ch in it for ch in short)


def match_subject(raw: str, subjects: Sequence[str]) -> str | None:
    """Название предмета из расписания, которое имела в виду модель, или None."""
    key = _norm(raw)
    if not key or not subjects:
        return None

    by_key = {_norm(s): s for s in subjects}
    if key in by_key:
        return by_key[key]

    prefixed = [s for k, s in by_key.items() if k.startswith(key) or key.startswith(k)]
    if len(prefixed) == 1:
        return prefixed[0]

    abbreviated = [s for k, s in by_key.items() if _is_abbreviation(key, k)]
    if len(abbreviated) == 1:
        return abbreviated[0]

    close = difflib.get_close_matches(key, list(by_key), n=1, cutoff=0.8)
    return by_key[close[0]] if close else None


def _tidy_subject(raw: str) -> str:
    raw = raw.strip()
    return raw[:1].upper() + raw[1:] if raw else ""


# ── Даты ─────────────────────────────────────────────────────────────────────

_WEEKDAY_STEMS = [
    ("понедельник", 0), ("пн", 0),
    ("вторник", 1), ("вт", 1),
    ("сред", 2), ("ср", 2),
    ("четверг", 3), ("чт", 3),
    ("пятниц", 4), ("пт", 4),
    ("суббот", 5), ("сб", 5),
    ("воскресен", 6), ("вс", 6),
]


def parse_due(raw: str | None, today: date) -> date | None:
    """
    Срок сдачи из ответа модели. Принимает ISO, «ДД.ММ», «ДД.ММ.ГГГГ»,
    «завтра» и дни недели — модели иногда возвращают слово вместо даты.
    Прошедшие и слишком далёкие даты отбрасываются: это ошибки чтения.
    """
    if not raw:
        return None
    s = raw.strip().lower()

    due: date | None = None

    iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    dotted = re.match(r"^(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?$", s)

    try:
        if iso:
            due = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        elif dotted:
            day, month = int(dotted.group(1)), int(dotted.group(2))
            year_raw   = dotted.group(3)
            if year_raw:
                year = int(year_raw) + (2000 if len(year_raw) == 2 else 0)
                due  = date(year, month, day)
            else:
                due = date(today.year, month, day)
                if due < today - timedelta(days=30):
                    due = date(today.year + 1, month, day)  # «к 15.01», сказанное в декабре
    except ValueError:
        return None

    if due is None:
        if s in ("сегодня",):
            due = today
        elif s in ("завтра", "на завтра"):
            due = today + timedelta(days=1)
        elif s in ("послезавтра",):
            due = today + timedelta(days=2)
        else:
            word = re.sub(r"^(на|к|ко|во|в)\s+", "", s)
            for stem, weekday in _WEEKDAY_STEMS:
                if word.startswith(stem):
                    ahead = (weekday - today.weekday()) % 7 or 7
                    due   = today + timedelta(days=ahead)
                    break

    if due is None or due < today or due > today + timedelta(days=_MAX_DUE_DAYS):
        return None
    return due


# ── Разбор ───────────────────────────────────────────────────────────────────

def resolve_items(
    raw_items: list[dict],
    schedule: ScheduleSource,
    subjects: Sequence[str],
    today: date,
) -> list[HomeworkItem]:
    """Сырые задания модели → проверенные записи с предметом и датой."""
    merged: dict[tuple[str, date | None], HomeworkItem] = {}

    for raw in raw_items:
        matched = match_subject(raw["subject"], subjects)
        subject = matched or _tidy_subject(raw["subject"]) or "Без предмета"

        due        = parse_due(raw.get("due_date"), today)
        due_source: DueSource = "explicit" if due else "none"
        if due is None:
            due = schedule.next_lesson(subject, today)
            if due:
                due_source = "schedule"

        key = (subject, due)
        if key in merged:
            # Модель разбила один предмет на несколько записей — склеиваем
            existing = merged[key]
            existing.task       = f"{existing.task}; {raw['task']}"
            existing.confidence = min(existing.confidence, raw["confidence"])
            continue

        merged[key] = HomeworkItem(
            subject=subject,
            task=raw["task"],
            due_date=due,
            due_source=due_source,
            confidence=raw["confidence"],
            in_schedule=matched is not None,
        )

    return list(merged.values())


async def analyze(
    *,
    text: str,
    images: Sequence[ImageInput],
    schedule: ScheduleSource,
    today: date,
    source: llm.HomeworkSource = "private",
    subjects: Sequence[str] | None = None,
) -> list[HomeworkItem]:
    """
    Все задания из сообщения. subjects — предметы для сопоставления;
    по умолчанию берутся из расписания.

    Ошибки модели (LLMUnavailable, LLMBadResponse) не глотаются: человек
    должен узнать, что разбор не удался, а не получить «заданий нет».
    """
    subjects  = list(subjects) if subjects is not None else schedule.subjects()
    raw_items = await llm.extract_homework(
        text=text, images=images, subjects=subjects, today=today, source=source,
    )
    return resolve_items(raw_items, schedule, subjects, today)
