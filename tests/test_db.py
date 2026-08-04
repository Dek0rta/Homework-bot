"""Тесты слоя БД на временном файле — реальный SQLite, без моков."""

import importlib

import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Свежая изолированная БД на каждый тест."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from src.core import config as config_mod
    importlib.reload(config_mod)
    from src.core import db as db_mod
    importlib.reload(db_mod)

    db_mod.init_db()
    from src.services import analytics
    importlib.reload(analytics)
    analytics.migrate_analytics_schema()
    return db_mod


def test_save_and_get_schedule(db):
    entries = [
        {"day": 0, "subject": "Математика", "start_time": "8:15"},
        {"day": 2, "subject": "Физика",     "start_time": "9:15"},
    ]
    db.save_schedule(1, entries)

    result = db.get_schedule(1)
    assert len(result) == 2
    assert db.has_schedule(1)
    assert {r["subject"] for r in result} == {"Математика", "Физика"}


def test_save_schedule_replaces_previous(db):
    db.save_schedule(1, [{"day": 0, "subject": "Старый", "start_time": "8:15"}])
    db.save_schedule(1, [{"day": 1, "subject": "Новый", "start_time": "9:15"}])

    result = db.get_schedule(1)
    assert len(result) == 1
    assert result[0]["subject"] == "Новый"


def test_schedules_are_isolated_per_user(db):
    db.save_schedule(1, [{"day": 0, "subject": "A", "start_time": "8:15"}])
    assert db.get_schedule(2) == []
    assert not db.has_schedule(2)


def test_homework_crud(db):
    hw_id = db.save_chat_homework(-100, "Физика", "§8 задачи 1-3", "2026-09-01")
    assert db.chat_homework_exists(-100, "Физика", "§8 задачи 1-3")

    items = db.get_chat_homework(-100)
    assert len(items) == 1
    assert items[0]["due_date"] == "2026-09-01"

    db.delete_chat_homework(hw_id)
    assert db.get_chat_homework(-100) == []


def test_homework_isolated_per_chat(db):
    db.save_chat_homework(-100, "Физика", "задача", None)
    assert db.get_chat_homework(-200) == []
    assert not db.chat_homework_exists(-200, "Физика", "задача")


def test_clear_chat_homework(db):
    db.save_chat_homework(-100, "A", "t1", None)
    db.save_chat_homework(-100, "B", "t2", None)
    db.clear_chat_homework(-100)
    assert db.get_chat_homework(-100) == []


def test_grade_belongs_to_blocks_other_users(db):
    """Ключевая проверка: чужую оценку удалить нельзя."""
    grade_id = db.save_grade(1, "Математика", 5, "2026-09-01")
    assert db.grade_belongs_to(grade_id, 1)
    assert not db.grade_belongs_to(grade_id, 2)


def test_grades_isolated_per_user(db):
    db.save_grade(1, "Математика", 5, "2026-09-01")
    assert len(db.get_grades(1)) == 1
    assert db.get_grades(2) == []


def test_grade_targets_upsert(db):
    db.set_grade_target(1, "Физика", 4)
    db.set_grade_target(1, "Физика", 5)  # перезапись, не дубль
    assert db.get_grade_targets(1) == {"Физика": 5}


def test_backup_roundtrip_preserves_data(db):
    db.save_schedule(1, [{"day": 0, "subject": "Математика", "start_time": "8:15"}])
    db.set_chat_subjects(-100, ["Математика", "Физика"])
    db.set_chat_schedule_owner(-100, 1)

    exported = db.export_critical_data()
    assert not db.is_db_empty()

    # Имитируем потерю диска
    conn = db.get_connection()
    conn.execute("DELETE FROM schedule")
    conn.execute("DELETE FROM chat_subjects")
    conn.execute("DELETE FROM chat_config")
    conn.commit()
    conn.close()
    assert db.is_db_empty()

    db.import_critical_data(exported)
    assert db.get_schedule(1)[0]["subject"] == "Математика"
    assert set(db.get_chat_subjects(-100)) == {"Математика", "Физика"}
    assert db.get_chat_schedule_owner(-100) == 1


def test_import_rejects_unknown_version(db):
    assert db.import_critical_data({"version": 99, "schedule": []}) == 0


# ── Изоляция классов ─────────────────────────────────────────────────────────

def test_schedule_for_chat_uses_owner(db):
    db.save_schedule(1, [{"day": 0, "subject": "Математика", "start_time": "8:15"}])
    db.set_chat_schedule_owner(-100, 1)

    result = db.get_schedule_for_chat(-100)
    assert len(result) == 1
    assert result[0]["subject"] == "Математика"


def test_schedule_for_chat_without_owner_is_empty(db):
    """
    Регрессия: раньше был фолбэк «первое расписание в БД» — класс без
    владельца получал чужое расписание.
    """
    db.save_schedule(1, [{"day": 0, "subject": "Математика", "start_time": "8:15"}])
    assert db.get_schedule_for_chat(-999) == []


def test_schedule_for_chat_isolates_two_classes(db):
    db.save_schedule(1, [{"day": 0, "subject": "Физика",  "start_time": "8:15"}])
    db.save_schedule(2, [{"day": 0, "subject": "Химия",   "start_time": "8:15"}])
    db.set_chat_schedule_owner(-100, 1)
    db.set_chat_schedule_owner(-200, 2)

    assert db.get_schedule_for_chat(-100)[0]["subject"] == "Физика"
    assert db.get_schedule_for_chat(-200)[0]["subject"] == "Химия"


def test_chats_for_user_finds_owned_chat(db):
    db.set_chat_schedule_owner(-100, 1)
    assert db.get_chats_for_user(1) == [-100]


def test_chats_for_user_finds_chat_via_homework_status(db):
    """Обычный ученик не владеет расписанием — связь через отметки о выполнении."""
    hw_id = db.save_chat_homework(-100, "Физика", "§8", "2026-09-01")

    conn = db.get_connection()
    conn.execute(
        "INSERT INTO user_homework_status (user_id, homework_id, is_done) VALUES (?,?,?)",
        (7, hw_id, 1),
    )
    conn.commit()
    conn.close()

    assert db.get_chats_for_user(7) == [-100]


def test_chats_for_unknown_user_is_empty(db):
    db.set_chat_schedule_owner(-100, 1)
    assert db.get_chats_for_user(42) == []


# ── Токены Google Calendar ───────────────────────────────────────────────────

def test_calendar_token_roundtrip(db):
    db.save_calendar_token(1, '{"token": "abc"}')
    assert db.has_calendar_token(1)
    assert db.get_calendar_token(1) == '{"token": "abc"}'
    assert db.get_calendar_id(1) == "primary"


def test_calendar_tokens_isolated_per_user(db):
    """Ключевая проверка: токен одного пользователя не виден другому."""
    db.save_calendar_token(1, '{"token": "user-one"}')
    assert db.get_calendar_token(2) is None
    assert not db.has_calendar_token(2)


def test_calendar_token_upsert_replaces(db):
    db.save_calendar_token(1, '{"token": "old"}')
    db.save_calendar_token(1, '{"token": "new"}')
    assert db.get_calendar_token(1) == '{"token": "new"}'


def test_calendar_token_custom_calendar_id(db):
    db.save_calendar_token(1, '{"token": "x"}', "work@group.calendar.google.com")
    assert db.get_calendar_id(1) == "work@group.calendar.google.com"


def test_delete_calendar_token(db):
    db.save_calendar_token(1, '{"token": "x"}')
    db.delete_calendar_token(1)
    assert not db.has_calendar_token(1)
    assert db.get_calendar_token(1) is None


def test_calendar_id_defaults_for_unknown_user(db):
    assert db.get_calendar_id(999) == "primary"


# ── Членство в чате ──────────────────────────────────────────────────────────

def test_remember_chat_member_makes_class_known(db):
    """
    Регрессия: ученик, который ничего не отмечал и не владеет расписанием,
    раньше был боту неизвестен и не получал ни расписания, ни графика.
    """
    assert db.get_chats_for_user(7) == []
    db.remember_chat_member(-100, 7)
    assert db.get_chats_for_user(7) == [-100]


def test_remember_chat_member_is_idempotent(db):
    db.remember_chat_member(-100, 7)
    db.remember_chat_member(-100, 7)
    assert db.get_chats_for_user(7) == [-100]


def test_member_of_two_chats(db):
    db.remember_chat_member(-100, 7)
    db.remember_chat_member(-200, 7)
    assert sorted(db.get_chats_for_user(7)) == [-200, -100]


def test_membership_does_not_leak_between_users(db):
    db.remember_chat_member(-100, 7)
    assert db.get_chats_for_user(8) == []


# ── Очередь ожидающих ДЗ ─────────────────────────────────────────────────────

def test_pending_homework_survives_and_is_taken_once(db):
    """
    Раньше очередь жила в словаре в памяти: рестарт бота терял задание,
    и кнопка отвечала «уже обработано». Теперь она в БД.
    """
    pending_id = db.save_pending_homework(-100, "Физика", "§8 задачи 1-3")

    taken = db.take_pending_homework(pending_id)
    assert taken["subject"] == "Физика"
    assert taken["task"] == "§8 задачи 1-3"
    assert taken["chat_id"] == -100

    # Повторное нажатие той же кнопки ничего не находит
    assert db.take_pending_homework(pending_id) is None


def test_take_unknown_pending_returns_none(db):
    assert db.take_pending_homework(12345) is None


def test_pending_entries_are_independent(db):
    first  = db.save_pending_homework(-100, "Физика", "задача 1")
    second = db.save_pending_homework(-100, "Химия",  "задача 2")

    assert db.take_pending_homework(first)["subject"] == "Физика"
    # Удаление первой не трогает вторую
    assert db.take_pending_homework(second)["subject"] == "Химия"


def test_purge_stale_pending_keeps_fresh(db):
    fresh = db.save_pending_homework(-100, "Физика", "свежая")

    conn = db.get_connection()
    conn.execute(
        "INSERT INTO pending_homework (chat_id, subject, task, created_at)"
        " VALUES (?,?,?,?)",
        (-100, "Химия", "старая", "2020-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    assert db.purge_stale_pending(older_than_days=7) == 1
    assert db.take_pending_homework(fresh) is not None


# ── Кеш оценок времени ───────────────────────────────────────────────────────

def test_estimate_cache_roundtrip(db):
    assert db.get_cached_estimate("hash-1") is None
    db.save_cached_estimate("hash-1", 45)
    assert db.get_cached_estimate("hash-1") == 45


def test_estimate_cache_upsert(db):
    db.save_cached_estimate("hash-1", 45)
    db.save_cached_estimate("hash-1", 60)
    assert db.get_cached_estimate("hash-1") == 60


def test_estimate_cache_keys_are_independent(db):
    db.save_cached_estimate("hash-1", 45)
    assert db.get_cached_estimate("hash-2") is None


# ── Общее расписание класса ──────────────────────────────────────────────────

LESSONS = [
    {"day": 0, "slot": 1, "subject": "Математика"},
    {"day": 0, "slot": 2, "subject": "Физика"},
    {"day": 1, "slot": 1, "subject": "Химия"},
]


def test_class_schedule_roundtrip(db):
    assert db.save_class_schedule(-100, LESSONS) == 3
    assert db.has_class_schedule(-100)

    result = db.get_class_schedule(-100)
    assert len(result) == 3
    assert result[0]["subject"] == "Математика"
    assert result[0]["day_of_week"] == 0
    assert result[0]["slot"] == 1


def test_class_schedule_derives_lesson_times(db):
    """Время урока выводится из номера — отдельно вводить его не нужно."""
    db.save_class_schedule(-100, LESSONS)
    result = db.get_class_schedule(-100)
    assert result[0]["start_time"] == "8:15"   # 1 урок
    assert result[1]["start_time"] == "9:15"   # 2 урок


def test_class_schedule_is_shared_by_all_members(db):
    """
    Суть продукта: настроил один — пользуются все.
    get_schedule_for_chat отдаёт расписание класса без личной настройки.
    """
    db.save_class_schedule(-100, LESSONS)
    assert len(db.get_schedule_for_chat(-100)) == 3
    # При этом ни у кого нет личного расписания
    assert not db.has_schedule(1)
    assert not db.has_schedule(2)


def test_class_schedule_replaces_previous(db):
    db.save_class_schedule(-100, LESSONS)
    db.save_class_schedule(-100, [{"day": 3, "slot": 1, "subject": "Биология"}])

    result = db.get_class_schedule(-100)
    assert len(result) == 1
    assert result[0]["subject"] == "Биология"


def test_class_schedules_isolated_between_chats(db):
    db.save_class_schedule(-100, LESSONS)
    db.save_class_schedule(-200, [{"day": 0, "slot": 1, "subject": "История"}])

    assert db.get_class_schedule(-100)[0]["subject"] == "Математика"
    assert db.get_class_schedule(-200)[0]["subject"] == "История"


def test_class_subjects_extracted_for_detection(db):
    """Предметы для детекции ДЗ берутся из расписания — /setup_subjects не нужен."""
    db.save_class_schedule(-100, LESSONS)
    assert sorted(db.get_class_subjects(-100)) == ["Математика", "Физика", "Химия"]


def test_class_subjects_deduplicated(db):
    db.save_class_schedule(-100, [
        {"day": 0, "slot": 1, "subject": "Математика"},
        {"day": 1, "slot": 1, "subject": "Математика"},
        {"day": 2, "slot": 1, "subject": "Физика"},
    ])
    assert sorted(db.get_class_subjects(-100)) == ["Математика", "Физика"]


def test_class_schedule_wins_over_owner_schedule(db):
    """Общее расписание класса приоритетнее личного расписания владельца."""
    db.save_schedule(1, [{"day": 0, "subject": "Личное", "start_time": "8:15"}])
    db.set_chat_schedule_owner(-100, 1)
    assert db.get_schedule_for_chat(-100)[0]["subject"] == "Личное"

    db.save_class_schedule(-100, LESSONS)
    assert db.get_schedule_for_chat(-100)[0]["subject"] == "Математика"


def test_empty_class_schedule_is_not_reported_as_set(db):
    assert not db.has_class_schedule(-999)
    assert db.get_class_schedule(-999) == []
