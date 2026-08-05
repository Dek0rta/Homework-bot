"""
REST API для Telegram Mini App (WebApp).
Монтируется на aiohttp-сервер из main.start_http_server().

Авторизация:
  Каждый запрос должен нести заголовок X-Telegram-Init-Data с подписанной
  Telegram строкой initData. user_id берётся из подписи, а НЕ из тела запроса —
  иначе любой мог бы читать и править чужие оценки.

Endpoints:
  GET    /api/homework               — все ДЗ (новые первыми)
  POST   /api/homework               — добавить ДЗ (JSON с base64-фото)
  PUT    /api/homework/{id}          — изменить ДЗ
  DELETE /api/homework/{id}          — удалить ДЗ
  GET    /api/status                 — карта { hwId: isDone } текущего пользователя
  POST   /api/status                 — отметить выполнение
  GET    /api/schedule               — расписание класса
  GET    /api/grades                 — оценки текущего пользователя
  POST   /api/grades                 — добавить оценку
  DELETE /api/grades/{id}            — удалить оценку
  GET    /api/grade-targets          — целевые баллы текущего пользователя
  POST   /api/grade-targets          — задать целевой балл
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from aiohttp import web

from src.api.auth import AuthError, authenticate
from src.core import db
from src.core.constants import lesson_number

logger = logging.getLogger(__name__)


# ── CORS ──────────────────────────────────────────────────────────────────────
#
# Origin ограничен адресом WebApp: с "*" любая сторонняя страница могла бы
# слать запросы от имени открывшего её пользователя.
#
# Запросы приходят из двух источников:
#   • Mini App внутри Telegram — Origin равен WEB_APP_URL
#   • сам Telegram (web.telegram.org) при открытии приложения в браузере
# Оба разрешены явным списком; всё остальное отклоняется.

_TELEGRAM_ORIGINS = frozenset({
    "https://web.telegram.org",
    "https://webk.telegram.org",
    "https://webz.telegram.org",
})


def _origin_of(url: str) -> str:
    """https://app.example.com/path → https://app.example.com (Origin без пути)."""
    if not url:
        return ""
    parsed = urlparse(url if "//" in url else f"https://{url}")
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def allowed_origins() -> frozenset[str]:
    configured = _origin_of(os.getenv("WEB_APP_URL", ""))
    return frozenset({configured} | set(_TELEGRAM_ORIGINS)) if configured else _TELEGRAM_ORIGINS


@web.middleware
async def cors_middleware(request: web.Request, handler):
    """
    Ставит CORS-заголовки на все ответы, включая ошибки и preflight.

    Origin запроса отражается, только если он в списке разрешённых.
    Этот заголовок ставит сам браузер и подделать его со страницы нельзя,
    поэтому отражение безопасно — и, в отличие от одного жёстко заданного
    значения, не ломает API, когда WEB_APP_URL не задан.
    """
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc

    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, X-Telegram-Init-Data, X-Debug-User-Id"
    )
    response.headers["Vary"] = "Origin"

    origin = request.headers.get("Origin", "")
    if origin and origin in allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin

    return response


def _json(data: Any, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        status=status,
    )


def _authed(handler):
    """
    Декоратор: проверяет подпись initData и передаёт доверенный user_id
    вторым аргументом. Неподписанный запрос получает 401.
    """
    async def wrapper(request: web.Request) -> web.Response:
        try:
            user_id = authenticate(request)
        except AuthError as exc:
            # Отсутствующий заголовок почти всегда означает устаревший фронт:
            # версии до введения проверки подписи его не отправляли.
            if not request.headers.get("X-Telegram-Init-Data"):
                logger.warning(
                    "Запрос без X-Telegram-Init-Data к %s — вероятно, WebApp "
                    "задеплоен старой версией и требует пересборки",
                    request.path,
                )
                return _json({
                    "error":  "unauthorized: missing initData",
                    "detail": "Приложение устарело. Закрой и открой его заново.",
                }, status=401)
            return _json({"error": f"unauthorized: {exc}"}, status=401)
        try:
            return await handler(request, user_id)
        except web.HTTPException:
            raise
        except Exception:
            logger.exception("Ошибка в %s", handler.__name__)
            return _json({"error": "internal error"}, status=500)

    wrapper.__name__ = handler.__name__
    return wrapper


# ── Определение класса пользователя ───────────────────────────────────────────

def _default_chat_id() -> int:
    """Чат класса из окружения. 0 — не задан (мультиклассовый режим)."""
    return int(os.getenv("WEBAPP_CHAT_ID", 0) or 0)


def _chats_for(user_id: int) -> list[int]:
    """
    Чаты, к которым относится пользователь, в порядке приоритета.
    WEBAPP_CHAT_ID остаётся как явное указание для установки на один класс,
    но больше не является единственным источником.
    """
    chats: list[int] = []

    explicit = _default_chat_id()
    if explicit:
        chats.append(explicit)

    for chat_id in db.get_chats_for_user(user_id):
        if chat_id not in chats:
            chats.append(chat_id)

    return chats


# ── Нормализация дат ──────────────────────────────────────────────────────────

def _norm_deadline(due_date: str | None) -> str:
    """Любой формат даты из БД → YYYY-MM-DD для фронтенда."""
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
    """Формат бота 'DD.MM HH:MM' → ISO 8601."""
    if not added_at:
        return datetime.now().isoformat()
    m = re.match(r"^(\d{1,2})\.(\d{2})\s+(\d{2}):(\d{2})$", added_at)
    if m:
        try:
            return datetime(
                date.today().year, int(m.group(2)), int(m.group(1)),
                int(m.group(3)), int(m.group(4)),
            ).isoformat()
        except ValueError as e:
            # Дата вида «31.02 10:00». Показать текущее время — меньшее зло,
            # чем уронить весь список, но молчать об этом нельзя.
            logger.warning("Некорректная дата создания ДЗ %r: %s", added_at, e)
    else:
        logger.warning("Неизвестный формат даты создания ДЗ: %r", added_at)
    return datetime.now().isoformat()


def _row_to_hw(row: Any) -> dict:
    photos: list[str] = []
    try:
        raw = row["photos_json"]
        if raw:
            photos = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        # Битый JSON: фото не показать, но и терять запись целиком не нужно.
        logger.warning("Повреждённый photos_json у ДЗ id=%s: %s", row["id"], e)
    except (IndexError, KeyError):
        photos = []  # старая схема без колонки
    try:
        confidence = row["ai_confidence"]
    except (IndexError, KeyError):
        confidence = None  # старая схема без колонки
    try:
        created_by = row["created_by"] or 0
    except (IndexError, KeyError):
        created_by = 0  # ДЗ создано до появления колонки — автор неизвестен
    return {
        "id":           str(row["id"]),
        "subject":      row["subject"],
        "description":  row["task"],
        "deadline":     _norm_deadline(row["due_date"]),
        "photos":       photos,
        "createdAt":    _norm_created_at(row["added_at"]),
        "createdBy":    created_by,
        "aiConfidence": confidence,
    }


# ── Домашние задания ──────────────────────────────────────────────────────────

@_authed
async def handle_get_homework(_request: web.Request, user_id: int) -> web.Response:
    """
    ДЗ класса пользователя. Раньше отдавались все записи таблицы,
    то есть задания всех классов сразу.

    chat_id=0 — задания, добавленные через WebApp без привязки к группе;
    они видны всем, так как принадлежность определить нельзя.
    """
    chat_ids = _chats_for(user_id) + [0]
    placeholders = ",".join("?" * len(chat_ids))

    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT id, subject, task, added_at, due_date, photos_json, ai_confidence, created_by "
            f"FROM chat_homework WHERE chat_id IN ({placeholders}) "
            "ORDER BY id DESC LIMIT 200",
            chat_ids,
        ).fetchall()
    finally:
        conn.close()
    return _json([_row_to_hw(r) for r in rows])


@_authed
async def handle_post_homework(request: web.Request, user_id: int) -> web.Response:
    data        = await request.json()
    subject     = str(data.get("subject",     "") or "").strip()
    description = str(data.get("description", "") or "").strip()
    deadline    = str(data.get("deadline",    "") or "").strip()
    photos      = data.get("photos", [])  # list[str] — base64 data-URI

    if not subject or not description:
        return _json({"error": "subject and description required"}, status=400)

    # Привязываем к классу автора; 0 — если класс определить не удалось
    chats   = _chats_for(user_id)
    chat_id = chats[0] if chats else 0
    hw_id   = db.save_chat_homework(
        chat_id, subject, description, deadline or None, created_by=user_id,
    )

    # Фото сохраняются отдельным update — save_chat_homework их не принимает
    if photos:
        db.update_chat_homework(hw_id, subject, description, deadline or None, json.dumps(photos))

    return _json({
        "id":          str(hw_id),
        "subject":     subject,
        "description": description,
        "deadline":    _norm_deadline(deadline),
        "photos":      photos,
        "createdAt":   datetime.now().isoformat(),
        "createdBy":   user_id,
    }, status=201)


@_authed
async def handle_put_homework(request: web.Request, _user_id: int) -> web.Response:
    hw_id       = int(request.match_info["id"])
    data        = await request.json()
    subject     = str(data.get("subject",     "") or "").strip()
    description = str(data.get("description", "") or "").strip()
    deadline    = str(data.get("deadline",    "") or "").strip()
    photos      = data.get("photos", [])

    if not subject or not description:
        return _json({"error": "subject and description required"}, status=400)

    db.update_chat_homework(
        hw_id, subject, description, deadline or None,
        json.dumps(photos) if photos else None,
    )

    return _json({
        "id":          str(hw_id),
        "subject":     subject,
        "description": description,
        "deadline":    _norm_deadline(deadline),
        "photos":      photos,
        "createdAt":   datetime.now().isoformat(),
        "createdBy":   0,
    })


@_authed
async def handle_delete_homework(request: web.Request, _user_id: int) -> web.Response:
    db.delete_chat_homework(int(request.match_info["id"]))
    return _json({"ok": True})


# ── Отметки о выполнении ──────────────────────────────────────────────────────

@_authed
async def handle_get_status(_request: web.Request, user_id: int) -> web.Response:
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT homework_id, is_done FROM user_homework_status WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return _json({str(r["homework_id"]): bool(r["is_done"]) for r in rows})


@_authed
async def handle_post_status(request: web.Request, user_id: int) -> web.Response:
    data        = await request.json()
    homework_id = int(data["homeworkId"])
    is_done     = bool(data["isDone"])

    conn = db.get_connection()
    try:
        conn.execute(
            "INSERT INTO user_homework_status (user_id, homework_id, is_done) VALUES (?,?,?)"
            " ON CONFLICT(user_id, homework_id) DO UPDATE SET is_done=excluded.is_done",
            (user_id, homework_id, 1 if is_done else 0),
        )
        conn.commit()
    finally:
        conn.close()
    return _json({"ok": True})


# ── Расписание ────────────────────────────────────────────────────────────────

@_authed
async def handle_get_schedule(_request: web.Request, user_id: int) -> web.Response:
    """
    Расписание, действующее для пользователя. Первый непустой источник:
      1. личное расписание пользователя
      2. расписание его класса (через chat_config.schedule_owner)

    Фолбэка «первое расписание в БД» здесь намеренно нет: он выдавал бы
    ученику одного класса расписание другого.
    """
    entries = db.get_schedule(user_id)

    if not entries:
        for chat_id in _chats_for(user_id):
            entries = db.get_schedule_for_chat(chat_id)
            if entries:
                break

    if not entries:
        return _json([])

    return _json([
        {
            "dayOfWeek":    e["day_of_week"],
            "lessonNumber": lesson_number(e["start_time"]),
            "startTime":    e["start_time"],
            "subject":      e["subject"],
        }
        for e in entries
    ])


# ── Оценки ────────────────────────────────────────────────────────────────────

@_authed
async def handle_get_grades(_request: web.Request, user_id: int) -> web.Response:
    return _json([
        {
            "id":      str(r["id"]),
            "userId":  r["user_id"],
            "subject": r["subject"],
            "value":   r["value"],
            "date":    r["date"],
            "note":    r.get("note"),
        }
        for r in db.get_grades(user_id)
    ])


@_authed
async def handle_post_grade(request: web.Request, user_id: int) -> web.Response:
    data    = await request.json()
    subject = str(data.get("subject", "") or "").strip()
    value   = int(data["value"])
    note    = str(data.get("note") or "").strip() or None

    if not subject:
        return _json({"error": "subject required"}, status=400)
    if value not in (2, 3, 4, 5):
        return _json({"error": "value must be 2–5"}, status=400)

    today    = date.today().isoformat()
    grade_id = db.save_grade(user_id, subject, value, today, note)
    return _json({
        "id":      str(grade_id),
        "userId":  user_id,
        "subject": subject,
        "value":   value,
        "date":    today,
        "note":    note,
    }, status=201)


@_authed
async def handle_delete_grade(request: web.Request, user_id: int) -> web.Response:
    grade_id = int(request.match_info["id"])
    # Удалять можно только свои оценки — id приходит от клиента и не доверен
    if not db.grade_belongs_to(grade_id, user_id):
        return _json({"error": "not found"}, status=404)
    db.delete_grade(grade_id)
    return _json({"ok": True})


@_authed
async def handle_get_grade_targets(_request: web.Request, user_id: int) -> web.Response:
    return _json(db.get_grade_targets(user_id))


@_authed
async def handle_post_grade_target(request: web.Request, user_id: int) -> web.Response:
    data    = await request.json()
    subject = str(data.get("subject", "") or "").strip()
    target  = int(data["target"])

    if not subject:
        return _json({"error": "subject required"}, status=400)
    if target not in (3, 4, 5):
        return _json({"error": "target must be 3, 4, or 5"}, status=400)

    db.set_grade_target(user_id, subject, target)
    return _json({"ok": True})


# ── Регистрация маршрутов ─────────────────────────────────────────────────────

def setup_webapp_routes(app: web.Application) -> None:
    app.router.add_get   ("/api/homework",      handle_get_homework)
    app.router.add_post  ("/api/homework",      handle_post_homework)
    app.router.add_put   ("/api/homework/{id}", handle_put_homework)
    app.router.add_delete("/api/homework/{id}", handle_delete_homework)

    app.router.add_get   ("/api/status",        handle_get_status)
    app.router.add_post  ("/api/status",        handle_post_status)

    app.router.add_get   ("/api/schedule",      handle_get_schedule)

    app.router.add_get   ("/api/grades",        handle_get_grades)
    app.router.add_post  ("/api/grades",        handle_post_grade)
    app.router.add_delete("/api/grades/{id}",   handle_delete_grade)

    app.router.add_get   ("/api/grade-targets", handle_get_grade_targets)
    app.router.add_post  ("/api/grade-targets", handle_post_grade_target)

    # Preflight и CORS-заголовки обслуживает cors_middleware,
    # подключённый при создании приложения.
    app.router.add_route("OPTIONS", "/api/{tail:.*}", lambda _r: web.Response(status=204))
