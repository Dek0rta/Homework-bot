"""
REST API endpoints for the Telegram Mini App (WebApp).
Mounted onto the existing aiohttp server inside bot.py's _start_keepalive().

Endpoints:
  GET  /api/homework              — all homework (aggregated across all chats)
  POST /api/homework              — add homework (multipart/form-data)
  GET  /api/status/{user_id}      — per-user completion map
  POST /api/status                — set one homework's completion status
  OPTIONS /api/*                  — CORS preflight
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
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
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

def _normalize_deadline(due_date: str | None) -> str:
    """Normalize any date string → YYYY-MM-DD required by the webapp."""
    if not due_date:
        return (date.today() + timedelta(days=1)).isoformat()
    # Already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", due_date):
        return due_date
    # DD.MM.YYYY
    m = re.match(r"^(\d{1,2})\.(\d{2})\.(\d{4})$", due_date)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"
    # DD.MM (assume current year)
    m = re.match(r"^(\d{1,2})\.(\d{2})$", due_date)
    if m:
        y = date.today().year
        return f"{y}-{m.group(2)}-{int(m.group(1)):02d}"
    return (date.today() + timedelta(days=1)).isoformat()


def _normalize_created_at(added_at: str | None) -> str:
    """Convert bot's 'DD.MM HH:MM' format → ISO 8601. Falls back to now."""
    if not added_at:
        return datetime.now().isoformat()
    m = re.match(r"^(\d{1,2})\.(\d{2})\s+(\d{2}):(\d{2})$", added_at)
    if m:
        d_day, d_mon, hh, mm = m.groups()
        y = date.today().year
        try:
            return datetime(y, int(d_mon), int(d_day), int(hh), int(mm)).isoformat()
        except ValueError:
            pass
    return datetime.now().isoformat()


# ── Route handlers ────────────────────────────────────────────────────────────

async def handle_get_homework(request: web.Request) -> web.Response:
    """Return all homework from all chats, newest first."""
    try:
        conn = db.get_connection()
        rows = conn.execute(
            "SELECT id, subject, task, added_at, due_date "
            "FROM chat_homework ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()
        result = [
            {
                "id":          str(row["id"]),
                "subject":     row["subject"],
                "description": row["task"],
                "deadline":    _normalize_deadline(row["due_date"]),
                "photos":      [],
                "createdAt":   _normalize_created_at(row["added_at"]),
                "createdBy":   0,
            }
            for row in rows
        ]
        return _json(result)
    except Exception as exc:
        return _json({"error": str(exc)}, status=500)


async def handle_post_homework(request: web.Request) -> web.Response:
    """Add a new homework entry (multipart/form-data)."""
    try:
        data        = await request.post()
        subject     = str(data.get("subject",     "") or "").strip()
        description = str(data.get("description", "") or "").strip()
        deadline    = str(data.get("deadline",    "") or "").strip()
        user_id     = int(data.get("userId", 0) or 0)

        if not subject or not description:
            return _json({"error": "subject and description are required"}, status=400)

        # Associate with a specific group if WEBAPP_CHAT_ID is set,
        # otherwise store under chat_id=0 (webapp-only homework).
        chat_id = int(os.getenv("WEBAPP_CHAT_ID", 0) or 0)
        hw_id   = db.save_chat_homework(chat_id, subject, description, deadline or None)

        return _json(
            {
                "id":          str(hw_id),
                "subject":     subject,
                "description": description,
                "deadline":    _normalize_deadline(deadline),
                "photos":      [],
                "createdAt":   datetime.now().isoformat(),
                "createdBy":   user_id,
            },
            status=201,
        )
    except Exception as exc:
        return _json({"error": str(exc)}, status=500)


async def handle_get_status(request: web.Request) -> web.Response:
    """Return { homeworkId: isDone } map for a given Telegram user."""
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
    """Persist one user's completion flag for one homework (upsert)."""
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


# ── Route registration ────────────────────────────────────────────────────────

def setup_webapp_routes(app: web.Application) -> None:
    """Register all WebApp API routes on an existing aiohttp Application."""
    app.router.add_get   ("/api/homework",         handle_get_homework)
    app.router.add_post  ("/api/homework",         handle_post_homework)
    app.router.add_get   ("/api/status/{user_id}", handle_get_status)
    app.router.add_post  ("/api/status",           handle_post_status)
    # CORS preflight for all /api/* paths
    app.router.add_route ("OPTIONS", "/api/{tail:.*}", _cors_preflight)
