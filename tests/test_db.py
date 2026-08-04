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


def test_get_all_group_chat_ids_reads_both_sources(db):
    """Регрессия: функция читает и chat_subjects, и daily_load_metrics."""
    db.set_chat_subjects(-100, ["Математика"])
    assert -100 in db.get_all_group_chat_ids()
