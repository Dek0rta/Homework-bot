"""
Разбор присланного ДЗ: предмет из расписания, дата сдачи, склейка дублей.

Модель здесь не вызывается — проверяется то, что код делает с её ответом.
Именно эта часть решает, попадёт ли задание на правильный день.
"""

from __future__ import annotations

import importlib
from datetime import date

import pytest

from src.services import homework_intake as intake
from src.services import llm

SATURDAY = date(2026, 10, 24)   # сегодня в тестах
MONDAY   = date(2026, 10, 26)
FRIDAY   = date(2026, 10, 30)

SUBJECTS = ["Алгебра", "Английский язык", "Литература", "Физика", "Физкультура", "Русский язык"]


# ── Предметы ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("Алгебра", "Алгебра"),
    ("алгебра", "Алгебра"),
    ("Англ. яз.", "Английский язык"),
    ("англ", "Английский язык"),
    ("английский", "Английский язык"),
    ("Лит-ра", "Литература"),
    ("физ-ра", "Физкультура"),
    ("Русский", "Русский язык"),
    ("Альгебра", "Алгебра"),          # опечатка
])
def test_match_subject(raw, expected):
    assert intake.match_subject(raw, SUBJECTS) == expected


@pytest.mark.parametrize("raw", ["История", "", "Физ"])
def test_match_subject_returns_none_when_ambiguous_or_absent(raw):
    """«Физ» подходит и к физике, и к физкультуре — не угадываем."""
    assert intake.match_subject(raw, SUBJECTS) is None


def test_match_subject_without_schedule():
    assert intake.match_subject("Алгебра", []) is None


# ── Даты ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("2026-10-30", FRIDAY),
    ("30.10", FRIDAY),
    ("30.10.2026", FRIDAY),
    ("30/10/26", FRIDAY),
    ("пятница", FRIDAY),
    ("на пятницу", FRIDAY),
    ("пт", FRIDAY),
    ("понедельник", MONDAY),
    ("завтра", date(2026, 10, 25)),
    ("сегодня", SATURDAY),
])
def test_parse_due(raw, expected):
    assert intake.parse_due(raw, SATURDAY) == expected


@pytest.mark.parametrize("raw", [
    None, "", "null", "к следующему уроку", "2026-10-20",  # прошлое
    "2027-12-01",                                          # слишком далеко
    "31.02",                                               # несуществующая дата
])
def test_parse_due_rejects_garbage(raw):
    assert intake.parse_due(raw, SATURDAY) is None


def test_same_weekday_means_next_week():
    """«В субботу», сказанное в субботу, — через неделю, а не сегодня."""
    assert intake.parse_due("суббота", SATURDAY) == date(2026, 10, 31)


def test_date_without_year_wraps_to_next_year():
    """«К 15.01», сказанное в декабре, — это январь следующего года."""
    assert intake.parse_due("15.01", date(2026, 12, 20)) == date(2027, 1, 15)


# ── Сопоставление с расписанием ──────────────────────────────────────────────

class FakeSchedule(intake.ScheduleSource):
    def __init__(self, lessons: dict[str, list[date]]):
        self._lessons = lessons

    def subjects(self):
        return list(self._lessons)

    def next_lessons(self, subject, after, n=3):
        return [d for d in self._lessons.get(subject, []) if d > after][:n]


def _raw(subject, task, due=None, confidence=0.9):
    return {"subject": subject, "task": task, "due_date": due, "confidence": confidence}


def test_explicit_date_beats_schedule():
    schedule = FakeSchedule({"Физика": [MONDAY]})
    [item] = intake.resolve_items([_raw("физика", "§12", "2026-10-30")], schedule, ["Физика"], SATURDAY)
    assert item.due_date == FRIDAY
    assert item.due_source == "explicit"


def test_no_date_falls_back_to_next_lesson():
    schedule = FakeSchedule({"Алгебра": [MONDAY, FRIDAY]})
    [item] = intake.resolve_items([_raw("алгебра", "№245")], schedule, ["Алгебра"], SATURDAY)
    assert item.subject == "Алгебра"
    assert item.due_date == MONDAY
    assert item.due_source == "schedule"
    assert item.in_schedule


def test_bad_explicit_date_falls_back_to_schedule():
    """Модель вернула прошедшую дату — это ошибка чтения, берём расписание."""
    schedule = FakeSchedule({"Алгебра": [MONDAY]})
    [item] = intake.resolve_items([_raw("Алгебра", "№1", "2026-10-01")], schedule, ["Алгебра"], SATURDAY)
    assert item.due_date == MONDAY


def test_unknown_subject_kept_without_date():
    [item] = intake.resolve_items([_raw("история", "п. 5")], FakeSchedule({}), [], SATURDAY)
    assert item.subject == "История"
    assert item.due_date is None
    assert item.due_source == "none"
    assert not item.in_schedule


def test_empty_subject_gets_placeholder():
    [item] = intake.resolve_items([_raw("", "выучить правило")], FakeSchedule({}), [], SATURDAY)
    assert item.subject == "Без предмета"


def test_same_subject_and_date_merged():
    schedule = FakeSchedule({"Алгебра": [MONDAY]})
    items = intake.resolve_items(
        [_raw("Алгебра", "№245", confidence=0.9), _raw("алгебра", "№247", confidence=0.5)],
        schedule, ["Алгебра"], SATURDAY,
    )
    assert len(items) == 1
    assert items[0].task == "№245; №247"
    assert items[0].confidence == 0.5
    assert items[0].needs_check


def test_same_subject_different_dates_kept_apart():
    schedule = FakeSchedule({"Алгебра": [MONDAY]})
    items = intake.resolve_items(
        [_raw("Алгебра", "№245"), _raw("Алгебра", "контрольная работа", "2026-10-30")],
        schedule, ["Алгебра"], SATURDAY,
    )
    assert [i.due_date for i in items] == [MONDAY, FRIDAY]


async def test_analyze_passes_schedule_subjects_to_model(monkeypatch):
    seen = {}

    async def fake_extract(**kwargs):
        seen.update(kwargs)
        return [_raw("англ яз", "WB p.34 ex.2")]

    monkeypatch.setattr(llm, "extract_homework", fake_extract)
    schedule = FakeSchedule({"Английский язык": [MONDAY]})

    [item] = await intake.analyze(
        text="англ WB p.34", images=[], schedule=schedule, today=SATURDAY,
    )
    assert seen["subjects"] == ["Английский язык"]
    assert seen["source"] == "private"
    assert item.subject == "Английский язык"
    assert item.due_date == MONDAY


# ── Ответ модели ─────────────────────────────────────────────────────────────

def test_normalize_homework_drops_empty_and_clamps():
    data = {"items": [
        {"subject": "Физика", "task": "  §8  ", "due_date": "null", "confidence": 3},
        {"subject": "Химия", "task": "", "due_date": None, "confidence": 0.9},
        "мусор",
    ]}
    assert llm.normalize_homework(data) == [
        {"subject": "Физика", "task": "§8", "due_date": None, "confidence": 1.0},
    ]


def test_normalize_homework_without_items():
    assert llm.normalize_homework({}) == []
    assert llm.normalize_homework({"items": "нет"}) == []


def test_extract_json_handles_wrapped_answer():
    assert llm._extract_json('```json\n{"items": []}\n```') == {"items": []}
    with pytest.raises(llm.LLMBadResponse):
        llm._extract_json("извините, не могу")


def test_prompt_contains_calendar_rules_and_text():
    prompt = llm.build_homework_prompt("алгебра №1", 2, ["Алгебра"], SATURDAY, "private")
    assert "пт 30.10 → 2026-10-30" in prompt
    assert "сб 24.10 → 2026-10-24 (сегодня)" in prompt
    assert "Предметы в расписании: Алгебра" in prompt
    assert "НА КОТОРЫЙ его задали" in prompt     # правило бумажного дневника
    assert "«алгебра №1»" in prompt
    assert "Фото в сообщении: 2" in prompt


def test_chat_prompt_explains_chitchat():
    prompt = llm.build_homework_prompt("кто сделал домашку?", 0, [], SATURDAY, "chat")
    assert "НЕ ДОМАШНЕЕ ЗАДАНИЕ" in prompt
    assert "Расписание не задано" in prompt


async def test_extract_homework_tiers(monkeypatch):
    """Личные ДЗ — точная модель; чат класса — быстрая или модель со зрением."""
    tiers = []

    class Router:
        async def complete(self, prompt, *, tier, images=(), schema=None, max_tokens=0):
            tiers.append(tier)
            return '{"items": []}'

    monkeypatch.setattr(llm, "get_router", lambda: Router())
    image = llm.ImageInput(b"x")

    await llm.extract_homework(text="x", today=SATURDAY, source="private")
    await llm.extract_homework(text="x", today=SATURDAY, source="chat")
    await llm.extract_homework(images=[image], today=SATURDAY, source="chat")
    assert tiers == ["smart", "fast", "vision"]


# ── Источники расписания на реальной БД ──────────────────────────────────────

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from src.core import config as config_mod
    importlib.reload(config_mod)
    from src.core import db as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()
    return db_mod


def test_personal_schedule_next_lessons(env):
    env.save_schedule(1, [
        {"day": 0, "subject": "Алгебра", "start_time": "8:15"},
        {"day": 3, "subject": "Алгебра", "start_time": "9:15"},
    ])
    schedule = intake.schedule_for_user(1)
    assert isinstance(schedule, intake.PersonalSchedule)
    assert schedule.next_lessons("алгебра", SATURDAY) == [
        MONDAY, date(2026, 10, 29), date(2026, 11, 2),
    ]


def test_class_schedule_skips_cancelled_lesson(env):
    """Отменённый урок не может быть датой сдачи — берём следующий."""
    chat = -100
    env.save_class_schedule(chat, [
        {"day": 0, "slot": 1, "subject": "Физика"},
        {"day": 4, "slot": 2, "subject": "Физика"},
    ])
    env.save_override(chat, MONDAY.isoformat(), 1, None, note="отмена")

    schedule = intake.ClassSchedule(chat)
    assert schedule.next_lesson("Физика", SATURDAY) == FRIDAY


def test_schedule_for_user_uses_class_when_no_personal(env):
    chat = -100
    env.save_class_schedule(chat, [{"day": 0, "slot": 1, "subject": "Химия"}])
    env.remember_chat_member(chat, 5)

    schedule = intake.schedule_for_user(5)
    assert isinstance(schedule, intake.ClassSchedule)
    assert schedule.subjects() == ["Химия"]


def test_schedule_for_user_without_any_schedule(env):
    schedule = intake.schedule_for_user(42)
    assert schedule.is_empty
    assert schedule.next_lesson("Алгебра", SATURDAY) is None


def test_schedule_for_chat_falls_back_to_owner(env):
    chat = -200
    env.save_schedule(7, [{"day": 2, "subject": "История", "start_time": "8:15"}])
    env.set_chat_schedule_owner(chat, 7)

    schedule = intake.schedule_for_chat(chat)
    assert schedule.next_lesson("История", SATURDAY) == date(2026, 10, 28)
