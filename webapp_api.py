"""
REST API endpoints for the Telegram Mini App (WebApp).
Mounted onto the existing aiohttp server inside bot.py's _start_keepalive().

Endpoints:
  GET    /api/homework              — all homework (newest first)
  POST   /api/homework              — add homework (JSON with base64 photos)
  PUT    /api/homework/{id}         — edit homework
  DELETE /api/homework/{id}         — delete homework
  GET    /api/status/{user_id}      — per-user { hwId: isDone } map
  POST   /api/status                — upsert one completion status
  GET    /api/schedule              — class timetable (from schedule_owner)
  OPTIONS /api/*                    — CORS preflight
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from typing import Any

from aiohttp import web

import db

# ── CORS ──────────────────────────────────────────────────────────────────────

CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


async def _cors_preflight(_request: web.Request) -> web.Response:
    return web.Response(status=204, headers=CORS_HEADERS)


def _json(data: Any, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        status=status,
        headers=CORS_HEADERS,
    )


# ── Date helpers ──────────────────────────────────────────────────────────────

def _norm_deadline(due_date: str | None) -> str:
    """Normalize any date string → YYYY-MM-DD for the webapp."""
    if not due_date:
        return (date.today() + timedelta(days=1)).isoformat()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", due_date):
        return due_date
    m = re.match(r"^(\d{1,2})\.(\d{2})\.(\d{4})$", due_date)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"
    m = re.match(r"^(\d{1,2})\.(\d{2})$", due_date)
    if m:
        return f"{date.today().year}-{m.group(2)}-{int(m.group(1)):02d}"
    return (date.today() + timedelta(days=1)).isoformat()


def _norm_created_at(added_at: str | None) -> str:
    """Convert bot's 'DD.MM HH:MM' → ISO 8601."""
    if not added_at:
        return datetime.now().isoformat()
    m = re.match(r"^(\d{1,2})\.(\d{2})\s+(\d{2}):(\d{2})$", added_at)
    if m:
        try:
            return datetime(
                date.today().year, int(m.group(2)), int(m.group(1)),
                int(m.group(3)), int(m.group(4)),
            ).isoformat()
        except ValueError:
            pass
    return datetime.now().isoformat()


def _row_to_hw(row: Any) -> dict:
    photos: list[str] = []
    try:
        raw = row["photos_json"]
        if raw:
            photos = json.loads(raw)
    except Exception:
        pass
    return {
        "id":          str(row["id"]),
        "subject":     row["subject"],
        "description": row["task"],
        "deadline":    _norm_deadline(row["due_date"]),
        "photos":      photos,
        "createdAt":   _norm_created_at(row["added_at"]),
        "createdBy":   0,
    }


# ── Lesson number lookup ──────────────────────────────────────────────────────

_LESSON_TIMES = [
    "8:15", "9:15", "10:10", "11:05", "12:00", "12:50", "13:40", "14:30",
]


def _lesson_number(start_time: str) -> int:
    try:
        return _LESSON_TIMES.index(start_time) + 1
    except ValueError:
        # Fallback: sort by time value
        for i, t in enumerate(_LESSON_TIMES, 1):
            if start_time <= t:
                return i
        return len(_LESSON_TIMES)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_get_homework(_request: web.Request) -> web.Response:
    try:
        conn = db.get_connection()
        rows = conn.execute(
            "SELECT id, subject, task, added_at, due_date, photos_json "
            "FROM chat_homework ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()
        return _json([_row_to_hw(r) for r in rows])
    except Exception as exc:
        return _json({"error": str(exc)}, status=500)


async def handle_post_homework(request: web.Request) -> web.Response:
    try:
        data        = await request.json()
        subject     = str(data.get("subject",     "") or "").strip()
        description = str(data.get("description", "") or "").strip()
        deadline    = str(data.get("deadline",    "") or "").strip()
        user_id     = int(data.get("userId", 0) or 0)
        photos      = data.get("photos", [])  # list[str] — base64 data-URIs

        if not subject or not description:
            return _json({"error": "subject and description required"}, status=400)

        photos_json = json.dumps(photos) if photos else None
        chat_id     = int(os.getenv("WEBAPP_CHAT_ID", 0) or 0)
        hw_id       = db.save_chat_homework(chat_id, subject, description, deadline or None)

        # Persist photos separately via update (save_chat_homework doesn't accept photos)
        if photos_json:
            db.update_chat_homework(hw_id, subject, description, deadline or None, photos_json)

        return _json(
            {
                "id":          str(hw_id),
                "subject":     subject,
                "description": description,
                "deadline":    _norm_deadline(deadline),
                "photos":      photos,
                "createdAt":   datetime.now().isoformat(),
                "createdBy":   user_id,
            },
            status=201,
        )
    except Exception as exc:
        return _json({"error": str(exc)}, status=500)


async def handle_put_homework(request: web.Request) -> web.Response:
    try:
        hw_id       = int(request.match_info["id"])
        data        = await request.json()
        subject     = str(data.get("subject",     "") or "").strip()
        description = str(data.get("description", "") or "").strip()
        deadline    = str(data.get("deadline",    "") or "").strip()
        photos      = data.get("photos", [])

        if not subject or not description:
            return _json({"error": "subject and description required"}, status=400)

        photos_json = json.dumps(photos) if photos else None
        db.update_chat_homework(hw_id, subject, description, deadline or None, photos_json)

        return _json({
            "id":          str(hw_id),
            "subject":     subject,
            "description": description,
            "deadline":    _norm_deadline(deadline),
            "photos":      photos,
            "createdAt":   datetime.now().isoformat(),
            "createdBy":   0,
        })
    except Exception as exc:
        return _json({"error": str(exc)}, status=500)


async def handle_delete_homework(request: web.Request) -> web.Response:
    try:
        hw_id = int(request.match_info["id"])
        db.delete_chat_homework(hw_id)
        return _json({"ok": True})
    except Exception as exc:
        return _json({"error": str(exc)}, status=500)


async def handle_get_status(request: web.Request) -> web.Response:
    try:
        user_id = int(request.match_info["user_id"])
        conn    = db.get_connection()
        rows    = conn.execute(
            "SELECT homework_id, is_done FROM user_homework_status WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        conn.close()
        return _json({str(r["homework_id"]): bool(r["is_done"]) for r in rows})
    except Exception:
        return _json({})


async def handle_post_status(request: web.Request) -> web.Response:
    try:
        data        = await request.json()
        user_id     = int(data["userId"])
        homework_id = int(data["homeworkId"])
        is_done     = bool(data["isDone"])
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO user_homework_status (user_id, homework_id, is_done) VALUES (?,?,?)"
            " ON CONFLICT(user_id, homework_id) DO UPDATE SET is_done=excluded.is_done",
            (user_id, homework_id, 1 if is_done else 0),
        )
        conn.commit()
        conn.close()
        return _json({"ok": True})
    except Exception as exc:
        return _json({"error": str(exc)}, status=500)


async def handle_get_schedule(_request: web.Request) -> web.Response:
    """Return class timetable.

    Strategy (first non-empty wins):
      1. schedule of WEBAPP_CHAT_ID's schedule_owner
      2. schedule of any user who has one (first by user_id — single-class bot)
    """
    try:
        entries = None

        # ── attempt 1: via WEBAPP_CHAT_ID ──────────────────────────────────
        chat_id = int(os.getenv("WEBAPP_CHAT_ID", 0) or 0)
        if chat_id:
            owner_id = db.get_chat_schedule_owner(chat_id)
            if owner_id:
                entries = db.get_schedule(owner_id) or None

        # ── attempt 2: first available schedule in DB ───────────────────────
        if not entries:
            conn = db.get_connection()
            row = conn.execute(
                "SELECT DISTINCT user_id FROM schedule ORDER BY user_id LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                entries = db.get_schedule(row["user_id"]) or None

        if not entries:
            return _json([])

        result = [
            {
                "dayOfWeek":    entry["day_of_week"],
                "lessonNumber": _lesson_number(entry["start_time"]),
                "startTime":    entry["start_time"],
                "subject":      entry["subject"],
            }
            for entry in entries
        ]
        return _json(result)
    except Exception:
        return _json([])  # frontend will fall back to mock


# ── Route registration ────────────────────────────────────────────────────────

def setup_webapp_routes(app: web.Application) -> None:
    app.router.add_get   ("/api/homework",          handle_get_homework)
    app.router.add_post  ("/api/homework",          handle_post_homework)
    app.router.add_put   ("/api/homework/{id}",     handle_put_homework)
    app.router.add_delete("/api/homework/{id}",     handle_delete_homework)
    app.router.add_get   ("/api/status/{user_id}",  handle_get_status)
    app.router.add_post  ("/api/status",            handle_post_status)
    app.router.add_get   ("/api/schedule",          handle_get_schedule)
    app.router.add_route ("OPTIONS", "/api/{tail:.*}", _cors_preflight)
