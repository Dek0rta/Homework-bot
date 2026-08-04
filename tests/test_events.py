"""Тесты журнала продуктовых событий."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from src.core import config as config_mod
    importlib.reload(config_mod)
    from src.core import db as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()
    return db_mod


def test_events_are_counted(db):
    db.log_event("bot_added", chat_id=-100)
    db.log_event("bot_added", chat_id=-200)
    db.log_event("homework_added", chat_id=-100)

    counts = db.event_counts()
    assert counts["bot_added"] == 2
    assert counts["homework_added"] == 1


def test_counts_are_empty_initially(db):
    assert db.event_counts() == {}


def test_payload_is_stored(db):
    db.log_event("schedule_saved", chat_id=-100, payload={"lessons": 30})

    conn = db.get_connection()
    row = conn.execute("SELECT payload FROM events WHERE event='schedule_saved'").fetchone()
    conn.close()
    assert "30" in row["payload"]


def test_logging_never_breaks_caller(db):
    """
    Аналитика не должна ронять основной сценарий: непригодный payload
    просто не записывается.
    """
    db.log_event("weird", payload={"obj": object()})  # не сериализуется в JSON
    # Исключения наружу не ушло — этого достаточно


def test_active_chats_counts_distinct(db):
    db.log_event("homework_added", chat_id=-100)
    db.log_event("homework_added", chat_id=-100)
    db.log_event("homework_added", chat_id=-200)

    since = (datetime.now() - timedelta(days=1)).isoformat()
    assert db.active_chats(since) == 2


def test_active_chats_respects_period(db):
    db.log_event("homework_added", chat_id=-100)
    future = (datetime.now() + timedelta(days=1)).isoformat()
    assert db.active_chats(future) == 0


def test_events_without_chat_not_counted_as_active(db):
    db.log_event("reminder_unsubscribed", user_id=5)
    since = (datetime.now() - timedelta(days=1)).isoformat()
    assert db.active_chats(since) == 0


def test_counts_can_be_limited_by_period(db):
    db.log_event("bot_added", chat_id=-100)

    past   = (datetime.now() - timedelta(days=1)).isoformat()
    future = (datetime.now() + timedelta(days=1)).isoformat()

    assert db.event_counts(past).get("bot_added") == 1
    assert db.event_counts(future).get("bot_added") is None


def test_funnel_events_are_distinguishable(db):
    """Воронка должна различать распознавание, сохранение и повторную попытку."""
    db.log_event("bot_added", chat_id=-100)
    db.log_event("schedule_recognized", chat_id=-100)
    db.log_event("schedule_retry", chat_id=-100)
    db.log_event("schedule_recognized", chat_id=-100)
    db.log_event("schedule_saved", chat_id=-100)

    counts = db.event_counts()
    assert counts["schedule_recognized"] == 2
    assert counts["schedule_retry"] == 1
    assert counts["schedule_saved"] == 1
