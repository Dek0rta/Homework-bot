"""Фото и альбомы: сборка альбома, перекодирование, дата пересланного."""

from __future__ import annotations

import asyncio
import io
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from PIL import Image

from src.bot import media

SATURDAY = date(2026, 10, 24)


def _msg(**kwargs):
    defaults = {"forward_origin": None, "text": None, "caption": None}
    return SimpleNamespace(**{**defaults, **kwargs})


# ── Дата пересланного сообщения ──────────────────────────────────────────────

def test_reference_day_for_regular_message():
    assert media.reference_day(_msg(), SATURDAY) == SATURDAY


def test_reference_day_uses_forward_date():
    """«На завтра», написанное в пятницу вечером по Москве, считается от пятницы."""
    friday_evening_utc = datetime(2026, 10, 23, 17, 0, tzinfo=timezone.utc)  # 20:00 МСК
    message = _msg(forward_origin=SimpleNamespace(date=friday_evening_utc))
    assert media.reference_day(message, SATURDAY) == date(2026, 10, 23)


def test_reference_day_converts_to_local_timezone():
    """22:30 UTC четверга — это уже пятница по Москве."""
    late_utc = datetime(2026, 10, 22, 22, 30, tzinfo=timezone.utc)
    message  = _msg(forward_origin=SimpleNamespace(date=late_utc))
    assert media.reference_day(message, SATURDAY) == date(2026, 10, 23)


def test_reference_day_ignores_old_forwards():
    old = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    assert media.reference_day(_msg(forward_origin=SimpleNamespace(date=old)), SATURDAY) == SATURDAY


def test_message_text_prefers_text_then_caption():
    assert media.message_text(_msg(text="  ДЗ  ")) == "ДЗ"
    assert media.message_text(_msg(caption="на пятницу")) == "на пятницу"
    assert media.message_text(_msg()) == ""


# ── Альбомы ──────────────────────────────────────────────────────────────────

async def test_album_collected_into_one_batch():
    collector = media.AlbumCollector(delay=0.05)
    messages  = [SimpleNamespace(media_group_id="g1", message_id=i) for i in (3, 1, 2)]

    results = await asyncio.gather(*(collector.collect(m) for m in messages))

    batches = [r for r in results if r is not None]
    assert len(batches) == 1
    assert [m.message_id for m in batches[0]] == [1, 2, 3]


async def test_different_albums_do_not_mix():
    collector = media.AlbumCollector(delay=0.05)
    a = SimpleNamespace(media_group_id="a", message_id=1)
    b = SimpleNamespace(media_group_id="b", message_id=2)

    results = await asyncio.gather(collector.collect(a), collector.collect(b))
    assert [[m.message_id for m in r] for r in results] == [[1], [2]]


# ── Перекодирование ──────────────────────────────────────────────────────────

def test_to_jpeg_converts_and_shrinks():
    buffer = io.BytesIO()
    Image.new("RGBA", (4000, 1000), (255, 0, 0, 128)).save(buffer, "WEBP")

    jpeg = media._to_jpeg(buffer.getvalue())

    with Image.open(io.BytesIO(jpeg)) as img:
        assert img.format == "JPEG"
        assert max(img.size) == 2560


def test_to_jpeg_rejects_non_image():
    with pytest.raises(media.UnsupportedImage):
        media._to_jpeg(b"definitely not an image")
