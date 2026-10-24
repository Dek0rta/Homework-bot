"""
Текущее время в часовом поясе школы.

Хостинг работает в UTC, а школа — по местному времени. С голым
datetime.now() после 21:00 по Москве «сегодня» на сервере уже завтра,
а проверка «урок уже прошёл» сдвинута на три часа. Поэтому всё, что
зависит от «сейчас», берёт время отсюда.

Возвращается naive datetime в местном времени: в БД и в сравнениях
по всему коду используются naive-значения, смешивать их с aware нельзя.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.config import TIMEZONE

logger = logging.getLogger(__name__)

_FALLBACK_TZ = "Europe/Moscow"


def _load_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Неизвестная TIMEZONE=%r — использую %s", name, _FALLBACK_TZ)
        return ZoneInfo(_FALLBACK_TZ)


_TZ = _load_zone(TIMEZONE)


def now() -> datetime:
    """Текущее местное время школы (naive)."""
    return datetime.now(_TZ).replace(tzinfo=None)


def today() -> date:
    """Сегодняшняя дата по местному времени школы."""
    return now().date()


def local_date(moment: datetime) -> date:
    """Дата момента по местному времени. Telegram отдаёт время в UTC."""
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(_TZ).date()
