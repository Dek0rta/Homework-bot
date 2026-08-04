"""
Тесты вечерних напоминаний.

Главные требования: не слать пустых сообщений, не слать дважды в день
и учитывать, что ученик уже отметил выполненным.
"""

from __future__ import annotations

import importlib
from datetime import date, timedelta

import pytest

CHAT = -100
USER = 777
TOMORROW = date.today() + timedelta(days=1)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from src.core import config as config_mod
    importlib.reload(config_mod)
    from src.core import db as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()

    from src.services import timetable as tt_mod
    importlib.reload(tt_mod)
    from src.services import reminders as rem_mod
    importlib.reload(rem_mod)
    return db_mod, rem_mod


def _add_hw(db, subject: str, task: str, minutes: int | None = None) -> int:
    hw_id = db.save_chat_homework(CHAT, subject, task, TOMORROW.isoformat())
    if minutes is not None:
        db.update_hw_estimated_time(hw_id, minutes)
    return hw_id


def _mark_done(db, hw_id: int, user_id: int = USER) -> None:
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO user_homework_status (user_id, homework_id, is_done) VALUES (?,?,1)",
        (user_id, hw_id),
    )
    conn.commit()
    conn.close()


# ── Содержимое напоминания ───────────────────────────────────────────────────

def test_reminder_lists_pending_homework(env):
    db, rem = env
    _add_hw(db, "Физика", "§8 задачи 1-3", 45)
    _add_hw(db, "Химия", "параграф 12", 30)

    text = rem.build_reminder(CHAT, USER, TOMORROW)
    assert text is not None
    assert "Физика" in text
    assert "Химия" in text
    assert "2 задания" in text


def test_no_reminder_when_nothing_due(env):
    """Пустых сообщений быть не должно — от них отписываются."""
    db, rem = env
    assert rem.build_reminder(CHAT, USER, TOMORROW) is None


def test_completed_homework_excluded(env):
    db, rem = env
    done_id = _add_hw(db, "Физика", "сделано", 30)
    _add_hw(db, "Химия", "не сделано", 30)
    _mark_done(db, done_id)

    text = rem.build_reminder(CHAT, USER, TOMORROW)
    assert "Химия" in text
    assert "Физика" not in text
    assert "1 задание" in text


def test_no_reminder_when_everything_done(env):
    db, rem = env
    hw_id = _add_hw(db, "Физика", "§8", 30)
    _mark_done(db, hw_id)
    assert rem.build_reminder(CHAT, USER, TOMORROW) is None


def test_completion_is_per_user(env):
    """Отметка одного ученика не должна убирать задание у другого."""
    db, rem = env
    hw_id = _add_hw(db, "Физика", "§8", 30)
    _mark_done(db, hw_id, user_id=USER)

    assert rem.build_reminder(CHAT, USER, TOMORROW) is None
    assert rem.build_reminder(CHAT, 888, TOMORROW) is not None


def test_time_estimate_is_summed(env):
    db, rem = env
    _add_hw(db, "Физика", "задача", 60)
    _add_hw(db, "Химия", "задача", 60)

    text = rem.build_reminder(CHAT, USER, TOMORROW)
    assert "~2 ч" in text


def test_missing_estimate_falls_back(env):
    """Без оценки LLM используется значение по умолчанию, а не ноль."""
    db, rem = env
    _add_hw(db, "Физика", "задача")  # оценки нет
    text = rem.build_reminder(CHAT, USER, TOMORROW)
    assert "мин" in text or "ч" in text


def test_heavy_day_gets_warning(env):
    db, rem = env
    for i in range(5):
        _add_hw(db, f"Предмет{i}", "большая задача", 60)

    text = rem.build_reminder(CHAT, USER, TOMORROW)
    assert "загруженный" in text


def test_light_day_has_no_warning(env):
    db, rem = env
    _add_hw(db, "Физика", "мелочь", 15)
    assert "загруженный" not in rem.build_reminder(CHAT, USER, TOMORROW)


def test_homework_from_other_chat_ignored(env):
    db, rem = env
    db.save_chat_homework(-999, "Чужой", "предмет", TOMORROW.isoformat())
    assert rem.build_reminder(CHAT, USER, TOMORROW) is None


# ── Подписки ─────────────────────────────────────────────────────────────────

def test_subscription_roundtrip(env):
    db, _ = env
    db.subscribe_reminders(USER, CHAT, "19:00")

    sub = db.get_subscription(USER)
    assert sub["chat_id"] == CHAT
    assert sub["send_at"] == "19:00"
    assert sub["enabled"] == 1


def test_unsubscribe_keeps_settings(env):
    """Отписка не должна терять выбранное время — вдруг вернётся."""
    db, _ = env
    db.subscribe_reminders(USER, CHAT, "21:00")
    db.unsubscribe_reminders(USER)

    sub = db.get_subscription(USER)
    assert sub["enabled"] == 0
    assert sub["send_at"] == "21:00"


def test_due_subscriptions_respects_time(env):
    db, _ = env
    db.subscribe_reminders(USER, CHAT, "19:00")
    today = date.today().isoformat()

    assert db.due_subscriptions("18:00", today) == []
    assert len(db.due_subscriptions("19:00", today)) == 1
    # Позже назначенного тоже отправляем — перезапуск не должен съедать напоминание
    assert len(db.due_subscriptions("20:30", today)) == 1


def test_not_sent_twice_a_day(env):
    db, _ = env
    db.subscribe_reminders(USER, CHAT, "19:00")
    today = date.today().isoformat()

    assert len(db.due_subscriptions("19:00", today)) == 1
    db.mark_reminder_sent(USER, today)
    assert db.due_subscriptions("19:00", today) == []


def test_sends_again_next_day(env):
    db, _ = env
    db.subscribe_reminders(USER, CHAT, "19:00")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    db.mark_reminder_sent(USER, yesterday)

    assert len(db.due_subscriptions("19:00", date.today().isoformat())) == 1


def test_disabled_subscription_never_due(env):
    db, _ = env
    db.subscribe_reminders(USER, CHAT, "19:00")
    db.unsubscribe_reminders(USER)
    assert db.due_subscriptions("19:00", date.today().isoformat()) == []


def test_subscriber_count_per_chat(env):
    db, _ = env
    db.subscribe_reminders(1, CHAT)
    db.subscribe_reminders(2, CHAT)
    db.subscribe_reminders(3, -200)

    assert db.count_subscribers(CHAT) == 2
    assert db.count_subscribers(-200) == 1
