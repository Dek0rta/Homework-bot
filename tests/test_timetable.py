"""
Тесты сборки расписания на день.

Здесь пересекаются три механики — чётность недель, подгруппы и замены,
поэтому проверяются и они по отдельности, и их совместная работа.
"""

from __future__ import annotations

import importlib
from datetime import date

import pytest

# Понедельник, объявленный нечётной неделей
MONDAY_ODD  = date(2026, 9, 7)
MONDAY_EVEN = date(2026, 9, 14)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Изолированная БД + модуль timetable поверх неё."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from src.core import config as config_mod
    importlib.reload(config_mod)
    from src.core import db as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()

    from src.services import timetable as tt_mod
    importlib.reload(tt_mod)
    return db_mod, tt_mod


CHAT = -100


# ── Базовое расписание ────────────────────────────────────────────────────────

def test_plain_schedule_on_matching_weekday(env):
    db, tt = env
    db.save_class_schedule(CHAT, [
        {"day": 0, "slot": 1, "subject": "Математика"},
        {"day": 0, "slot": 2, "subject": "Физика"},
        {"day": 1, "slot": 1, "subject": "Химия"},
    ])

    lessons = tt.lessons_on(CHAT, MONDAY_ODD)
    assert [l["subject"] for l in lessons] == ["Математика", "Физика"]


def test_day_without_lessons_is_empty(env):
    db, tt = env
    db.save_class_schedule(CHAT, [{"day": 0, "slot": 1, "subject": "Математика"}])
    # Воскресенье
    assert tt.lessons_on(CHAT, date(2026, 9, 13)) == []


# ── Подгруппы ─────────────────────────────────────────────────────────────────

def test_both_subgroups_share_one_slot(env):
    """Ключевой случай: в одном слоте два предмета для разных подгрупп."""
    db, tt = env
    db.save_class_schedule(CHAT, [
        {"day": 0, "slot": 1, "subject": "Английский", "subgroup": 1},
        {"day": 0, "slot": 1, "subject": "Английский", "subgroup": 2},
    ])
    assert len(tt.lessons_on(CHAT, MONDAY_ODD)) == 2


def test_student_sees_only_own_subgroup(env):
    db, tt = env
    db.save_class_schedule(CHAT, [
        {"day": 0, "slot": 1, "subject": "Информатика", "subgroup": 1},
        {"day": 0, "slot": 1, "subject": "Технология",  "subgroup": 2},
        {"day": 0, "slot": 2, "subject": "Математика",  "subgroup": 0},
    ])

    first = tt.lessons_on(CHAT, MONDAY_ODD, subgroup=1)
    assert [l["subject"] for l in first] == ["Информатика", "Математика"]

    second = tt.lessons_on(CHAT, MONDAY_ODD, subgroup=2)
    assert [l["subject"] for l in second] == ["Технология", "Математика"]


def test_common_lessons_visible_to_every_subgroup(env):
    db, tt = env
    db.save_class_schedule(CHAT, [{"day": 0, "slot": 1, "subject": "Математика", "subgroup": 0}])
    for group in (0, 1, 2):
        assert len(tt.lessons_on(CHAT, MONDAY_ODD, subgroup=group)) == 1


# ── Чётность недель ───────────────────────────────────────────────────────────

def test_alternating_lessons_swap_between_weeks(env):
    db, tt = env
    db.save_class_schedule(CHAT, [
        {"day": 0, "slot": 1, "subject": "Алгебра",   "week_parity": "odd"},
        {"day": 0, "slot": 1, "subject": "Геометрия", "week_parity": "even"},
    ])
    db.set_parity_anchor(CHAT, MONDAY_ODD.isoformat())

    assert [l["subject"] for l in tt.lessons_on(CHAT, MONDAY_ODD)]  == ["Алгебра"]
    assert [l["subject"] for l in tt.lessons_on(CHAT, MONDAY_EVEN)] == ["Геометрия"]


def test_without_anchor_both_variants_shown(env):
    """Пока неделя не указана, скрывать уроки нельзя — показываем оба."""
    db, tt = env
    db.save_class_schedule(CHAT, [
        {"day": 0, "slot": 1, "subject": "Алгебра",   "week_parity": "odd"},
        {"day": 0, "slot": 1, "subject": "Геометрия", "week_parity": "even"},
    ])
    assert len(tt.lessons_on(CHAT, MONDAY_ODD)) == 2


def test_weekly_lessons_unaffected_by_parity(env):
    db, tt = env
    db.save_class_schedule(CHAT, [{"day": 0, "slot": 1, "subject": "Математика"}])
    db.set_parity_anchor(CHAT, MONDAY_ODD.isoformat())

    assert len(tt.lessons_on(CHAT, MONDAY_ODD)) == 1
    assert len(tt.lessons_on(CHAT, MONDAY_EVEN)) == 1


# ── Замены ────────────────────────────────────────────────────────────────────

def test_override_replaces_subject(env):
    db, tt = env
    db.save_class_schedule(CHAT, [{"day": 0, "slot": 1, "subject": "Физика"}])
    db.save_override(CHAT, MONDAY_ODD.isoformat(), slot=1, subject="История")

    lesson = tt.lessons_on(CHAT, MONDAY_ODD)[0]
    assert lesson["subject"] == "История"
    assert lesson["is_override"]
    assert not lesson["is_cancelled"]


def test_override_can_cancel_lesson(env):
    db, tt = env
    db.save_class_schedule(CHAT, [{"day": 0, "slot": 1, "subject": "Физика"}])
    db.save_override(CHAT, MONDAY_ODD.isoformat(), slot=1, subject=None)

    lesson = tt.lessons_on(CHAT, MONDAY_ODD)[0]
    assert lesson["is_cancelled"]
    assert lesson["subject"] == "Физика"  # показываем, что именно отменили


def test_override_applies_only_to_its_date(env):
    db, tt = env
    db.save_class_schedule(CHAT, [{"day": 0, "slot": 1, "subject": "Физика"}])
    db.save_override(CHAT, MONDAY_ODD.isoformat(), slot=1, subject="История")

    # Следующий понедельник — обычная физика
    assert tt.lessons_on(CHAT, MONDAY_EVEN)[0]["subject"] == "Физика"


def test_deleting_override_restores_schedule(env):
    db, tt = env
    db.save_class_schedule(CHAT, [{"day": 0, "slot": 1, "subject": "Физика"}])
    db.save_override(CHAT, MONDAY_ODD.isoformat(), slot=1, subject="История")
    db.delete_override(CHAT, MONDAY_ODD.isoformat(), slot=1)

    assert tt.lessons_on(CHAT, MONDAY_ODD)[0]["subject"] == "Физика"


def test_override_for_one_subgroup_leaves_other_intact(env):
    db, tt = env
    db.save_class_schedule(CHAT, [
        {"day": 0, "slot": 1, "subject": "Английский", "subgroup": 1},
        {"day": 0, "slot": 1, "subject": "Английский", "subgroup": 2},
    ])
    db.save_override(CHAT, MONDAY_ODD.isoformat(), slot=1, subject="Немецкий", subgroup=1)

    lessons = {l["subgroup"]: l["subject"] for l in tt.lessons_on(CHAT, MONDAY_ODD)}
    assert lessons[1] == "Немецкий"
    assert lessons[2] == "Английский"


# ── Совместная работа механик ────────────────────────────────────────────────

def test_parity_subgroup_and_override_combined(env):
    """
    Реалистичный случай: подгруппы, чередование по неделям и замена
    на конкретную дату — всё одновременно.
    """
    db, tt = env
    db.save_class_schedule(CHAT, [
        {"day": 0, "slot": 1, "subject": "Английский", "subgroup": 1},
        {"day": 0, "slot": 1, "subject": "Английский", "subgroup": 2},
        {"day": 0, "slot": 2, "subject": "Алгебра",    "week_parity": "odd"},
        {"day": 0, "slot": 2, "subject": "Геометрия",  "week_parity": "even"},
        {"day": 0, "slot": 3, "subject": "История"},
    ])
    db.set_parity_anchor(CHAT, MONDAY_ODD.isoformat())
    db.save_override(CHAT, MONDAY_ODD.isoformat(), slot=3, subject=None)  # историю отменили

    lessons = tt.lessons_on(CHAT, MONDAY_ODD, subgroup=1)
    assert [l["subject"] for l in lessons] == ["Английский", "Алгебра", "История"]
    assert lessons[0]["subgroup"] == 1          # своя подгруппа
    assert lessons[1]["subject"] == "Алгебра"   # нечётная неделя
    assert lessons[2]["is_cancelled"]           # отменена заменой


def test_format_day_renders_all_markers(env):
    db, tt = env
    db.save_class_schedule(CHAT, [
        {"day": 0, "slot": 1, "subject": "Английский", "subgroup": 1},
        {"day": 0, "slot": 2, "subject": "Алгебра",    "week_parity": "odd"},
        {"day": 0, "slot": 3, "subject": "История"},
    ])
    db.set_parity_anchor(CHAT, MONDAY_ODD.isoformat())
    db.save_override(CHAT, MONDAY_ODD.isoformat(), slot=3, subject=None)

    text = tt.format_day(CHAT, MONDAY_ODD)
    assert "Английский" in text
    assert "1 группа" in text
    assert "числитель" in text
    assert "отменён" in text
