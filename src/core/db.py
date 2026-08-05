from __future__ import annotations
import logging
import sqlite3
import os
from datetime import datetime, timedelta

from src.core.config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            subject     TEXT    NOT NULL,
            start_time  TEXT    NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_homework (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id  INTEGER NOT NULL,
            subject  TEXT    NOT NULL,
            task     TEXT    NOT NULL,
            added_at TEXT    NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_subjects (
            chat_id INTEGER NOT NULL,
            subject TEXT    NOT NULL,
            PRIMARY KEY (chat_id, subject)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_config (
            chat_id           INTEGER PRIMARY KEY,
            schedule_owner_id INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_homework_status (
            user_id     INTEGER NOT NULL,
            homework_id INTEGER NOT NULL,
            is_done     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, homework_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT    NOT NULL,
            value   INTEGER NOT NULL,
            date    TEXT    NOT NULL,
            note    TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grade_targets (
            user_id INTEGER NOT NULL,
            subject TEXT    NOT NULL,
            target  INTEGER NOT NULL,
            PRIMARY KEY (user_id, subject)
        )
    """)
    # OAuth-токен Google Calendar на каждого пользователя.
    # Раньше токен был один на весь бот (data/token.json), поэтому ДЗ всех
    # учеников попадали в календарь того, кто авторизовался первым.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_calendar_tokens (
            user_id     INTEGER PRIMARY KEY,
            token_json  TEXT    NOT NULL,
            calendar_id TEXT    NOT NULL DEFAULT 'primary',
            updated_at  TEXT    NOT NULL
        )
    """)
    # Членство в чатах. Пишется при первом же сообщении пользователя в группе,
    # поэтому класс известен ещё до того, как ученик что-то отметил.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_members (
            chat_id   INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            seen_at   TEXT    NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    # Расписание класса — общее для всех участников чата.
    # Один ученик настраивает, остальные пользуются без своего сетапа.
    # Личное расписание (таблица schedule) остаётся для тех, кто хочет своё.
    #
    # Один слот может содержать несколько записей:
    #   • подгруппы — «Английский 1 группа» и «Английский 2 группа» одновременно
    #   • чётность  — «Алгебра» по числителю, «Геометрия» по знаменателю
    # Поэтому в ключе участвуют subgroup и week_parity.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS class_schedule (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            slot        INTEGER NOT NULL,
            subject     TEXT    NOT NULL,
            subgroup    INTEGER NOT NULL DEFAULT 0,  -- 0=весь класс, 1..n=подгруппа
            week_parity TEXT    NOT NULL DEFAULT '', -- ''=каждую неделю, 'odd'|'even'
            UNIQUE(chat_id, day_of_week, slot, subgroup, week_parity)
        )
    """)
    # Замены на конкретную дату: отмена урока или подмена предмета.
    # Живут отдельно от расписания, чтобы не портить постоянную сетку.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedule_overrides (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    INTEGER NOT NULL,
            date       TEXT    NOT NULL,          -- YYYY-MM-DD
            slot       INTEGER NOT NULL,
            subgroup   INTEGER NOT NULL DEFAULT 0,
            subject    TEXT,                      -- NULL = урок отменён
            note       TEXT,
            created_at TEXT    NOT NULL,
            UNIQUE(chat_id, date, slot, subgroup)
        )
    """)
    # Подгруппа ученика: кто в какой группе по английскому и т.п.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_subgroups (
            chat_id  INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            subgroup INTEGER NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    # Опорная дата отсчёта чётности недель для класса.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS class_settings (
            chat_id           INTEGER PRIMARY KEY,
            parity_anchor     TEXT,     -- YYYY-MM-DD понедельника нечётной недели
            updated_at        TEXT NOT NULL
        )
    """)
    # Подписка на вечерние напоминания.
    # Telegram не даёт боту писать первым, поэтому подписка возможна только
    # после того, как пользователь сам открыл личный чат с ботом.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminder_subscriptions (
            user_id     INTEGER PRIMARY KEY,
            chat_id     INTEGER NOT NULL,   -- класс, о котором напоминаем
            send_at     TEXT    NOT NULL DEFAULT '19:00',
            enabled     INTEGER NOT NULL DEFAULT 1,
            last_sent   TEXT,               -- YYYY-MM-DD, чтобы не слать дважды
            created_at  TEXT    NOT NULL
        )
    """)
    # Журнал продуктовых событий. Нужен, чтобы видеть, где отваливаются
    # пользователи, и не гадать о причинах. Без текстов сообщений.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event      TEXT    NOT NULL,
            chat_id    INTEGER,
            user_id    INTEGER,
            payload    TEXT,               -- JSON с числами, без личных данных
            created_at TEXT    NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_event_date ON events(event, created_at)"
    )
    # ДЗ, ожидающие выбора дня сдачи. Раньше лежали в словаре в памяти —
    # рестарт бота терял их, и кнопка отвечала «задание уже обработано».
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_homework (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    INTEGER NOT NULL,
            subject    TEXT    NOT NULL,
            task       TEXT    NOT NULL,
            created_at TEXT    NOT NULL
        )
    """)
    # Кеш LLM-оценок времени выполнения. Ключ — нормализованный текст задания,
    # поэтому одинаковые ДЗ не оплачиваются повторно.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hw_time_estimates (
            task_hash  TEXT    PRIMARY KEY,
            minutes    INTEGER NOT NULL,
            created_at TEXT    NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_homework_chat ON chat_homework(chat_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_user ON schedule(user_id)"
    )
    # Миграции: добавляем колонки если таблицы уже существуют без них
    for migration in [
        "ALTER TABLE chat_homework ADD COLUMN due_date TEXT",
        "ALTER TABLE chat_homework ADD COLUMN photos_json TEXT",
        "ALTER TABLE chat_homework ADD COLUMN estimated_time_minutes INTEGER",
        "ALTER TABLE chat_homework ADD COLUMN ai_confidence REAL",
        # Подгруппы и чётность недель добавлены позже создания class_schedule
        "ALTER TABLE class_schedule ADD COLUMN subgroup INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE class_schedule ADD COLUMN week_parity TEXT NOT NULL DEFAULT ''",
        # ДЗ может относиться только к одной подгруппе
        "ALTER TABLE chat_homework ADD COLUMN subgroup INTEGER NOT NULL DEFAULT 0",
        # Автор задания: 0 — добавлено ботом из чата либо до появления колонки
        "ALTER TABLE chat_homework ADD COLUMN created_by INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError as e:
            # Колонка уже существует — обычный случай на непустой БД.
            # Всё остальное (нет таблицы, битый SQL) скрывать нельзя.
            if "duplicate column name" not in str(e).lower():
                logger.warning("Миграция не применена (%s): %s", migration, e)
    conn.commit()
    conn.close()


def save_schedule(user_id: int, entries: list[dict]):
    """entries = [{"day": 0, "subject": "Математика", "start_time": "8:00"}, ...]"""
    conn = get_connection()
    conn.execute("DELETE FROM schedule WHERE user_id = ?", (user_id,))
    conn.executemany(
        "INSERT INTO schedule (user_id, day_of_week, subject, start_time) VALUES (?, ?, ?, ?)",
        [(user_id, e["day"], e["subject"], e["start_time"]) for e in entries],
    )
    conn.commit()
    conn.close()


def get_schedule(user_id: int) -> list[dict]:
    conn = get_connection()
    cur = conn.execute(
        "SELECT day_of_week, subject, start_time FROM schedule "
        "WHERE user_id = ? ORDER BY day_of_week, start_time",
        (user_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def has_schedule(user_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("SELECT 1 FROM schedule WHERE user_id = ? LIMIT 1", (user_id,))
    result = cur.fetchone()
    conn.close()
    return result is not None


# ── Групповое ДЗ ────────────────────────────────────────────────────────────

def save_chat_homework(
    chat_id: int,
    subject: str,
    task: str,
    due_date: str | None = None,
    ai_confidence: float | None = None,
    created_by: int = 0,
) -> int:
    """
    Сохраняет ДЗ и возвращает id новой записи.

    created_by — автор задания; 0, если ДЗ распознано ботом из сообщения чата
    и конкретного автора у него нет.
    """
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO chat_homework"
        " (chat_id, subject, task, added_at, due_date, ai_confidence, created_by)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chat_id, subject, task, datetime.now().strftime("%d.%m %H:%M"),
         due_date, ai_confidence, created_by),
    )
    hw_id = cur.lastrowid
    conn.commit()
    conn.close()
    return hw_id


def update_hw_estimated_time(hw_id: int, minutes: int) -> None:
    """Сохраняет оценку времени (от LLM) для конкретного задания."""
    conn = get_connection()
    conn.execute(
        "UPDATE chat_homework SET estimated_time_minutes=? WHERE id=?",
        (minutes, hw_id),
    )
    conn.commit()
    conn.close()


def get_chat_homework(chat_id: int) -> list[dict]:
    conn = get_connection()
    cur = conn.execute(
        "SELECT id, subject, task, added_at, due_date FROM chat_homework "
        "WHERE chat_id = ? ORDER BY id DESC LIMIT 50",
        (chat_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def chat_homework_exists(chat_id: int, subject: str, task: str) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "SELECT 1 FROM chat_homework WHERE chat_id=? AND subject=? AND task=? LIMIT 1",
        (chat_id, subject, task),
    )
    result = cur.fetchone()
    conn.close()
    return result is not None


def update_chat_homework(
    hw_id: int,
    subject: str,
    task: str,
    due_date: str | None,
    photos_json: str | None,
) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE chat_homework SET subject=?, task=?, due_date=?, photos_json=? WHERE id=?",
        (subject, task, due_date, photos_json, hw_id),
    )
    conn.commit()
    conn.close()


def delete_chat_homework(hw_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM chat_homework WHERE id = ?", (hw_id,))
    conn.commit()
    conn.close()


def clear_chat_homework(chat_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM chat_homework WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def get_chat_subjects(chat_id: int) -> list[str]:
    conn = get_connection()
    cur = conn.execute(
        "SELECT subject FROM chat_subjects WHERE chat_id = ? ORDER BY subject",
        (chat_id,),
    )
    rows = [r["subject"] for r in cur.fetchall()]
    conn.close()
    return rows


def set_chat_schedule_owner(chat_id: int, owner_id: int):
    conn = get_connection()
    conn.execute(
        "INSERT INTO chat_config (chat_id, schedule_owner_id) VALUES (?, ?)"
        " ON CONFLICT(chat_id) DO UPDATE SET schedule_owner_id=excluded.schedule_owner_id",
        (chat_id, owner_id),
    )
    conn.commit()
    conn.close()


def save_class_schedule(chat_id: int, lessons: list[dict]) -> int:
    """
    Сохраняет расписание класса целиком, заменяя прежнее.

    lessons = [{"day", "slot", "subject", "subgroup"?, "week_parity"?}, ...]
    subgroup    — 0 (весь класс) или номер подгруппы
    week_parity — "" | "odd" | "even"

    Возвращает число сохранённых уроков.
    """
    conn = get_connection()
    conn.execute("DELETE FROM class_schedule WHERE chat_id = ?", (chat_id,))
    conn.executemany(
        "INSERT OR REPLACE INTO class_schedule"
        " (chat_id, day_of_week, slot, subject, subgroup, week_parity)"
        " VALUES (?,?,?,?,?,?)",
        [
            (
                chat_id, l["day"], l["slot"], l["subject"],
                int(l.get("subgroup", 0) or 0),
                str(l.get("week_parity", "") or ""),
            )
            for l in lessons
        ],
    )
    conn.commit()
    conn.close()
    return len(lessons)


def get_class_schedule(chat_id: int, subgroup: int | None = None) -> list[dict]:
    """
    Расписание класса в формате, совместимом с личным.

    subgroup:
      None — всё расписание целиком, включая обе подгруппы
      n    — только уроки всего класса (subgroup=0) и подгруппы n
    """
    from src.core.constants import LESSON_TIMES

    query = (
        "SELECT day_of_week, slot, subject, subgroup, week_parity FROM class_schedule"
        " WHERE chat_id = ?"
    )
    params: list = [chat_id]

    if subgroup is not None:
        query += " AND subgroup IN (0, ?)"
        params.append(subgroup)

    query += " ORDER BY day_of_week, slot, subgroup"

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [
        {
            "day_of_week": r["day_of_week"],
            "subject":     r["subject"],
            "start_time":  LESSON_TIMES[r["slot"] - 1] if 1 <= r["slot"] <= len(LESSON_TIMES) else "",
            "slot":        r["slot"],
            "subgroup":    r["subgroup"],
            "week_parity": r["week_parity"],
        }
        for r in rows
    ]


# ── Подгруппа ученика ────────────────────────────────────────────────────────

def set_user_subgroup(chat_id: int, user_id: int, subgroup: int) -> None:
    """Запоминает, в какой подгруппе учится пользователь."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO user_subgroups (chat_id, user_id, subgroup) VALUES (?,?,?)"
        " ON CONFLICT(chat_id, user_id) DO UPDATE SET subgroup=excluded.subgroup",
        (chat_id, user_id, subgroup),
    )
    conn.commit()
    conn.close()


def get_user_subgroup(chat_id: int, user_id: int) -> int:
    """Подгруппа пользователя. 0 — не выбрана, показываем всё."""
    conn = get_connection()
    row = conn.execute(
        "SELECT subgroup FROM user_subgroups WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    ).fetchone()
    conn.close()
    return row["subgroup"] if row else 0


def get_schedule_subgroups(chat_id: int) -> list[int]:
    """Номера подгрупп, встречающихся в расписании класса (без нулевой)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT subgroup FROM class_schedule"
        " WHERE chat_id = ? AND subgroup > 0 ORDER BY subgroup",
        (chat_id,),
    ).fetchall()
    conn.close()
    return [r["subgroup"] for r in rows]


# ── Чётность недель ──────────────────────────────────────────────────────────

def set_parity_anchor(chat_id: int, anchor_date: str) -> None:
    """Опорный понедельник нечётной недели — от него считается чётность."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO class_settings (chat_id, parity_anchor, updated_at) VALUES (?,?,?)"
        " ON CONFLICT(chat_id) DO UPDATE SET"
        "   parity_anchor=excluded.parity_anchor, updated_at=excluded.updated_at",
        (chat_id, anchor_date, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_parity_anchor(chat_id: int) -> str | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT parity_anchor FROM class_settings WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    conn.close()
    return row["parity_anchor"] if row and row["parity_anchor"] else None


def schedule_has_parity(chat_id: int) -> bool:
    """Есть ли в расписании уроки, зависящие от чётности недели."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM class_schedule WHERE chat_id = ? AND week_parity != '' LIMIT 1",
        (chat_id,),
    ).fetchone()
    conn.close()
    return row is not None


# ── Замены уроков ────────────────────────────────────────────────────────────

def save_override(
    chat_id: int,
    date_iso: str,
    slot: int,
    subject: str | None,
    subgroup: int = 0,
    note: str | None = None,
) -> None:
    """
    Замена на конкретную дату. subject=None означает отмену урока.
    Постоянное расписание при этом не меняется.
    """
    conn = get_connection()
    conn.execute(
        "INSERT INTO schedule_overrides (chat_id, date, slot, subgroup, subject, note, created_at)"
        " VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(chat_id, date, slot, subgroup) DO UPDATE SET"
        "   subject=excluded.subject, note=excluded.note, created_at=excluded.created_at",
        (chat_id, date_iso, slot, subgroup, subject, note, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_overrides(chat_id: int, date_iso: str) -> list[dict]:
    """Замены на конкретную дату."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT slot, subgroup, subject, note FROM schedule_overrides"
        " WHERE chat_id = ? AND date = ? ORDER BY slot, subgroup",
        (chat_id, date_iso),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_override(chat_id: int, date_iso: str, slot: int, subgroup: int = 0) -> None:
    """Отменяет замену — урок возвращается к постоянному расписанию."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM schedule_overrides"
        " WHERE chat_id = ? AND date = ? AND slot = ? AND subgroup = ?",
        (chat_id, date_iso, slot, subgroup),
    )
    conn.commit()
    conn.close()


def purge_old_overrides(before_date: str) -> int:
    """Удаляет замены за прошедшие даты. Возвращает их число."""
    conn = get_connection()
    cur = conn.execute("DELETE FROM schedule_overrides WHERE date < ?", (before_date,))
    conn.commit()
    conn.close()
    return cur.rowcount


# ── Подписка на напоминания ──────────────────────────────────────────────────

def subscribe_reminders(user_id: int, chat_id: int, send_at: str = "19:00") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO reminder_subscriptions (user_id, chat_id, send_at, enabled, created_at)"
        " VALUES (?,?,?,1,?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        "   chat_id=excluded.chat_id, send_at=excluded.send_at, enabled=1",
        (user_id, chat_id, send_at, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def unsubscribe_reminders(user_id: int) -> None:
    """Выключает напоминания, не теряя настройки времени."""
    conn = get_connection()
    conn.execute("UPDATE reminder_subscriptions SET enabled=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def get_subscription(user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id, chat_id, send_at, enabled, last_sent"
        " FROM reminder_subscriptions WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def due_subscriptions(now_hhmm: str, today_iso: str) -> list[dict]:
    """
    Подписки, которым пора отправить напоминание: время наступило и сегодня
    ещё не отправляли. Сравнение по «<=», чтобы пропущенная минута
    (перезапуск, лаг) не съедала напоминание целиком.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT user_id, chat_id, send_at FROM reminder_subscriptions"
        " WHERE enabled = 1 AND send_at <= ?"
        "   AND (last_sent IS NULL OR last_sent < ?)",
        (now_hhmm, today_iso),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_reminder_sent(user_id: int, today_iso: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE reminder_subscriptions SET last_sent=? WHERE user_id=?",
        (today_iso, user_id),
    )
    conn.commit()
    conn.close()


def count_subscribers(chat_id: int) -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) FROM reminder_subscriptions WHERE chat_id=? AND enabled=1",
        (chat_id,),
    ).fetchone()
    conn.close()
    return row[0]


# ── Журнал событий ───────────────────────────────────────────────────────────

def log_event(
    event: str,
    chat_id: int | None = None,
    user_id: int | None = None,
    payload: dict | None = None,
) -> None:
    """
    Записывает продуктовое событие. Тексты сообщений и заданий сюда не
    попадают — только счётчики и идентификаторы, чтобы журнал оставался
    безопасным для анализа.
    """
    import json as _json

    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO events (event, chat_id, user_id, payload, created_at)"
            " VALUES (?,?,?,?,?)",
            (
                event,
                chat_id,
                user_id,
                _json.dumps(payload, ensure_ascii=False) if payload else None,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # аналитика не должна ломать основной сценарий


def event_counts(since_iso: str | None = None) -> dict[str, int]:
    """Сколько раз случилось каждое событие — основа продуктовых метрик."""
    conn = get_connection()
    if since_iso:
        rows = conn.execute(
            "SELECT event, COUNT(*) FROM events WHERE created_at >= ? GROUP BY event",
            (since_iso,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT event, COUNT(*) FROM events GROUP BY event").fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def active_chats(since_iso: str) -> int:
    """Число классов, где что-то происходило после указанной даты."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(DISTINCT chat_id) FROM events"
        " WHERE chat_id IS NOT NULL AND created_at >= ?",
        (since_iso,),
    ).fetchone()
    conn.close()
    return row[0]


def has_class_schedule(chat_id: int) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM class_schedule WHERE chat_id = ? LIMIT 1", (chat_id,)
    ).fetchone()
    conn.close()
    return row is not None


def get_class_subjects(chat_id: int) -> list[str]:
    """Уникальные предметы из расписания класса — для автонастройки детекции ДЗ."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT subject FROM class_schedule WHERE chat_id = ? ORDER BY subject",
        (chat_id,),
    ).fetchall()
    conn.close()
    return [r["subject"] for r in rows]


def get_schedule_for_chat(chat_id: int) -> list[dict]:
    """
    Расписание, действующее для чата. Приоритет:
      1. общее расписание класса (class_schedule)
      2. личное расписание назначенного владельца — для обратной совместимости

    Намеренно без фолбэка «первое расписание в БД»: он выдавал бы одному
    классу расписание другого.
    """
    class_entries = get_class_schedule(chat_id)
    if class_entries:
        return class_entries

    owner_id = get_chat_schedule_owner(chat_id)
    return get_schedule(owner_id) if owner_id else []


def remember_chat_member(chat_id: int, user_id: int) -> None:
    """
    Отмечает, что пользователь писал в этот чат. Вызывается на каждом
    сообщении в группе, поэтому класс известен сразу, а не после первой
    отметки о выполнении ДЗ.
    """
    conn = get_connection()
    conn.execute(
        "INSERT INTO chat_members (chat_id, user_id, seen_at) VALUES (?,?,?)"
        " ON CONFLICT(chat_id, user_id) DO UPDATE SET seen_at=excluded.seen_at",
        (chat_id, user_id, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_chats_for_user(user_id: int) -> list[int]:
    """
    Чаты, к которым относится пользователь. Источники, в порядке надёжности:
      1. он писал в чат (chat_members)
      2. он владелец расписания чата
      3. он отмечал в чате выполнение ДЗ

    Нужен, чтобы понять, какому классу отдавать расписание, ДЗ и графики.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT chat_id FROM chat_members WHERE user_id = ?"
        " UNION "
        "SELECT chat_id FROM chat_config WHERE schedule_owner_id = ?"
        " UNION "
        "SELECT DISTINCT h.chat_id FROM chat_homework h"
        " JOIN user_homework_status s ON s.homework_id = h.id"
        " WHERE s.user_id = ?",
        (user_id, user_id, user_id),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── ДЗ, ожидающие подтверждения дня ──────────────────────────────────────────

def save_pending_homework(chat_id: int, subject: str, task: str) -> int:
    """Кладёт ДЗ в очередь ожидания и возвращает её id для callback_data."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO pending_homework (chat_id, subject, task, created_at) VALUES (?,?,?,?)",
        (chat_id, subject, task, datetime.now().isoformat()),
    )
    pending_id = cur.lastrowid
    conn.commit()
    conn.close()
    return pending_id


def take_pending_homework(pending_id: int) -> dict | None:
    """
    Достаёт и удаляет запись очереди. None — если её уже обработали
    (например, двойным нажатием кнопки).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT chat_id, subject, task FROM pending_homework WHERE id = ?",
            (pending_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM pending_homework WHERE id = ?", (pending_id,))
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def purge_stale_pending(older_than_days: int = 7) -> int:
    """Убирает записи, на которые никто так и не нажал. Возвращает их число."""
    cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
    conn = get_connection()
    cur = conn.execute("DELETE FROM pending_homework WHERE created_at < ?", (cutoff,))
    conn.commit()
    conn.close()
    return cur.rowcount


# ── Кеш оценок времени ────────────────────────────────────────────────────────

def get_cached_estimate(task_hash: str) -> int | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT minutes FROM hw_time_estimates WHERE task_hash = ?",
        (task_hash,),
    ).fetchone()
    conn.close()
    return row["minutes"] if row else None


def save_cached_estimate(task_hash: str, minutes: int) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO hw_time_estimates (task_hash, minutes, created_at) VALUES (?,?,?)"
        " ON CONFLICT(task_hash) DO UPDATE SET minutes=excluded.minutes",
        (task_hash, minutes, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_chat_schedule_owner(chat_id: int) -> int | None:
    conn = get_connection()
    cur = conn.execute("SELECT schedule_owner_id FROM chat_config WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return row["schedule_owner_id"] if row else None


def is_db_empty() -> bool:
    """True если в БД нет ни одного расписания и ни одного предмета группы."""
    conn = get_connection()
    has_sched = conn.execute("SELECT 1 FROM schedule LIMIT 1").fetchone()
    has_subj  = conn.execute("SELECT 1 FROM chat_subjects LIMIT 1").fetchone()
    conn.close()
    return not has_sched and not has_subj


def export_critical_data() -> dict:
    """
    Экспортирует критические данные (расписание, предметы групп, конфиг)
    в словарь для сохранения как env var SCHEDULE_BACKUP.
    Намеренно НЕ включает chat_homework — ДЗ эфемерны по природе.
    """
    conn = get_connection()
    data = {
        "version": 2,
        "schedule": [
            dict(r) for r in conn.execute(
                "SELECT user_id, day_of_week, subject, start_time FROM schedule"
            ).fetchall()
        ],
        "chat_subjects": [
            dict(r) for r in conn.execute(
                "SELECT chat_id, subject FROM chat_subjects"
            ).fetchall()
        ],
        "chat_config": [
            dict(r) for r in conn.execute(
                "SELECT chat_id, schedule_owner_id FROM chat_config"
            ).fetchall()
        ],
    }
    conn.close()
    return data


def import_critical_data(data: dict) -> int:
    """
    Восстанавливает данные из словаря (результат export_critical_data).
    Возвращает количество вставленных записей. Дубликаты игнорируются.
    """
    if not isinstance(data, dict) or data.get("version") not in (1, 2):
        return 0

    conn = get_connection()
    total = 0

    schedule = data.get("schedule", [])
    if schedule:
        conn.executemany(
            "INSERT OR IGNORE INTO schedule (user_id, day_of_week, subject, start_time)"
            " VALUES (?, ?, ?, ?)",
            [(r["user_id"], r["day_of_week"], r["subject"], r["start_time"]) for r in schedule],
        )
        total += len(schedule)

    subjects = data.get("chat_subjects", [])
    if subjects:
        conn.executemany(
            "INSERT OR IGNORE INTO chat_subjects (chat_id, subject) VALUES (?, ?)",
            [(r["chat_id"], r["subject"]) for r in subjects],
        )
        total += len(subjects)

    config = data.get("chat_config", [])
    if config:
        conn.executemany(
            "INSERT OR IGNORE INTO chat_config (chat_id, schedule_owner_id) VALUES (?, ?)",
            [(r["chat_id"], r["schedule_owner_id"]) for r in config],
        )
        total += len(config)

    conn.commit()
    conn.close()
    return total


def set_chat_subjects(chat_id: int, subjects: list[str]):
    conn = get_connection()
    conn.execute("DELETE FROM chat_subjects WHERE chat_id = ?", (chat_id,))
    conn.executemany(
        "INSERT INTO chat_subjects (chat_id, subject) VALUES (?, ?)",
        [(chat_id, s) for s in subjects],
    )
    conn.commit()
    conn.close()


# ── Grades (personal per-user) ───────────────────────────────────────────────

def save_grade(
    user_id: int,
    subject: str,
    value: int,
    date: str,
    note: str | None = None,
) -> int:
    """Сохраняет оценку и возвращает её id."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO grades (user_id, subject, value, date, note) VALUES (?,?,?,?,?)",
        (user_id, subject, value, date, note),
    )
    grade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return grade_id


def get_grades(user_id: int) -> list[dict]:
    """Возвращает все оценки пользователя (новые сначала)."""
    conn = get_connection()
    cur = conn.execute(
        "SELECT id, user_id, subject, value, date, note FROM grades"
        " WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def grade_belongs_to(grade_id: int, user_id: int) -> bool:
    """True если оценка принадлежит пользователю. Защита от правки чужих записей."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM grades WHERE id = ? AND user_id = ? LIMIT 1",
        (grade_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def delete_grade(grade_id: int) -> None:
    """Удаляет оценку по id."""
    conn = get_connection()
    conn.execute("DELETE FROM grades WHERE id = ?", (grade_id,))
    conn.commit()
    conn.close()


def set_grade_target(user_id: int, subject: str, target: int) -> None:
    """Устанавливает целевой балл по предмету для пользователя."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO grade_targets (user_id, subject, target) VALUES (?,?,?)"
        " ON CONFLICT(user_id, subject) DO UPDATE SET target=excluded.target",
        (user_id, subject, target),
    )
    conn.commit()
    conn.close()


def get_grade_targets(user_id: int) -> dict[str, int]:
    """Возвращает словарь {предмет: целевой_балл} для пользователя."""
    conn = get_connection()
    cur = conn.execute(
        "SELECT subject, target FROM grade_targets WHERE user_id = ?",
        (user_id,),
    )
    result = {r["subject"]: r["target"] for r in cur.fetchall()}
    conn.close()
    return result


# ── Токены Google Calendar (на пользователя) ─────────────────────────────────

def save_calendar_token(user_id: int, token_json: str, calendar_id: str = "primary") -> None:
    """Сохраняет (или обновляет) OAuth-токен пользователя."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO user_calendar_tokens (user_id, token_json, calendar_id, updated_at)"
        " VALUES (?,?,?,?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        "   token_json=excluded.token_json,"
        "   calendar_id=excluded.calendar_id,"
        "   updated_at=excluded.updated_at",
        (user_id, token_json, calendar_id, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_calendar_token(user_id: int) -> str | None:
    """Сырой JSON токена пользователя или None, если он не авторизован."""
    conn = get_connection()
    row = conn.execute(
        "SELECT token_json FROM user_calendar_tokens WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["token_json"] if row else None


def get_calendar_id(user_id: int) -> str:
    """Календарь, в который пишет пользователь. По умолчанию — primary."""
    conn = get_connection()
    row = conn.execute(
        "SELECT calendar_id FROM user_calendar_tokens WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["calendar_id"] if row and row["calendar_id"] else "primary"


def has_calendar_token(user_id: int) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM user_calendar_tokens WHERE user_id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return row is not None


def delete_calendar_token(user_id: int) -> None:
    """Отвязывает Google Calendar от пользователя."""
    conn = get_connection()
    conn.execute("DELETE FROM user_calendar_tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
