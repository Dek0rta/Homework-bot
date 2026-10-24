"""
Личные ДЗ на реальной БД: хранение, правка пачкой, видимость в Mini App
и в напоминаниях.

Личное задание хранится в chat_homework с chat_id = user_id, поэтому главное
здесь — изоляция: правка и удаление не должны задевать чужие записи.
"""

from __future__ import annotations

import importlib
from datetime import date, timedelta

import pytest

USER  = 777
OTHER = 888
CLASS = -100


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("WEBAPP_CHAT_ID", raising=False)

    from src.core import config as config_mod
    importlib.reload(config_mod)
    from src.core import db as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()

    from src.services import timetable, reminders
    importlib.reload(timetable)
    importlib.reload(reminders)
    from src.api import webapp_api
    return db_mod, reminders, webapp_api


def test_range_is_limited_to_owner(env):
    """Диапазон id пачки не захватывает задания других пользователей между ними."""
    db, _, _ = env
    a = db.save_chat_homework(USER, "Алгебра", "№1", None, created_by=USER)
    foreign = db.save_chat_homework(OTHER, "Физика", "§2", None, created_by=OTHER)
    b = db.save_chat_homework(USER, "Химия", "№3", None, created_by=USER)

    assert [r["id"] for r in db.get_homework_range(USER, a, b)] == [a, b]
    assert db.delete_homework_range(USER, a, b) == 2
    assert db.get_homework(foreign) is not None


def test_set_due_and_done(env):
    db, _, _ = env
    hw = db.save_chat_homework(USER, "Алгебра", "№1", None, created_by=USER)

    db.set_homework_due(hw, "2026-10-30")
    assert db.get_homework(hw)["due_date"] == "2026-10-30"

    assert not db.is_homework_done(USER, hw)
    db.set_homework_done(USER, hw, True)
    assert db.is_homework_done(USER, hw)
    db.set_homework_done(USER, hw, False)
    assert not db.is_homework_done(USER, hw)


def test_upcoming_homework_order_and_filter(env):
    db, _, _ = env
    old    = db.save_chat_homework(USER, "А", "старое", "2026-01-01")
    later  = db.save_chat_homework(USER, "Б", "позже", "2026-10-30")
    sooner = db.save_chat_homework(CLASS, "В", "раньше", "2026-10-26")
    nodate = db.save_chat_homework(USER, "Г", "без даты", None)
    db.save_chat_homework(OTHER, "Д", "чужое", "2026-10-27")
    db.set_homework_done(USER, later, True)

    rows = db.get_upcoming_homework([USER, CLASS], USER, "2026-10-24")
    assert [r["id"] for r in rows] == [sooner, later, nodate]
    assert old not in [r["id"] for r in rows]
    assert [r["is_done"] for r in rows] == [0, 1, 0]


def test_webapp_shows_personal_homework_only_to_owner(env):
    db, _, api = env
    mine = db.save_chat_homework(USER, "Алгебра", "№1", None, created_by=USER)

    assert USER in api._visible_chats(USER)
    assert api._can_modify(mine, USER)
    assert not api._can_modify(mine, OTHER)   # чужое личное задание не править
    assert not api._can_modify(999_999, USER)  # несуществующее


def test_webapp_class_homework_editable_by_classmates(env):
    db, _, api = env
    db.remember_chat_member(CLASS, OTHER)
    hw = db.save_chat_homework(CLASS, "Физика", "§2", None)

    assert api._can_modify(hw, OTHER)
    assert not api._can_modify(hw, USER)       # не состоит в классе


def test_reminder_includes_personal_homework(env):
    db, reminders, _ = env
    tomorrow = date.today() + timedelta(days=1)
    db.save_chat_homework(CLASS, "Физика", "§8", tomorrow.isoformat())
    db.save_chat_homework(USER, "Алгебра", "№245", tomorrow.isoformat(), created_by=USER)
    db.save_chat_homework(OTHER, "Химия", "чужое", tomorrow.isoformat(), created_by=OTHER)

    text = reminders.build_reminder(CLASS, USER, tomorrow)
    assert "Физика" in text
    assert "Алгебра" in text
    assert "Химия" not in text


def test_reminder_without_class_uses_personal_schedule(env):
    """Подписка без класса (chat_id = user_id) показывает уроки из личного расписания."""
    db, reminders, _ = env
    tomorrow = date.today() + timedelta(days=1)
    db.save_schedule(USER, [{"day": tomorrow.weekday(), "subject": "Алгебра", "start_time": "8:15"}])
    db.save_chat_homework(USER, "Алгебра", "№245", tomorrow.isoformat(), created_by=USER)

    text = reminders.build_reminder(USER, USER, tomorrow)
    assert "Уроки: Алгебра" in text
