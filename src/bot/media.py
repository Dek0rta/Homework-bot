"""
Фото и альбомы из сообщений Telegram — в вид, понятный модели.

Альбом приходит в бот россыпью: каждое фото отдельным сообщением с общим
media_group_id. Если разбирать их по одному, домашка с двух страниц дневника
превращается в два независимых разбора и две карточки. Поэтому сообщения
альбома собираются в пачку и разбираются одним запросом.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import date

from aiogram.types import Message

from src.core import clock
from src.services.llm_providers import ImageInput

logger = logging.getLogger(__name__)

# Форматы, которые модель принимает как есть
_NATIVE_MIME = {"image/jpeg", "image/png"}

# GigaChat принимает файлы до 15 МБ; Telegram отдаёт ботам до 20 МБ
MAX_IMAGE_BYTES = 15 * 1024 * 1024

# Больше этого по длинной стороне модели не нужно — только медленнее загрузка
_MAX_SIDE = 2560


class UnsupportedImage(ValueError):
    """Файл не удаётся превратить в изображение для модели."""


def message_text(message: Message) -> str:
    return (message.text or message.caption or "").strip()


# Пересланное старше этого — относительные даты в нём уже не пересчитать
_MAX_FORWARD_AGE_DAYS = 14


def reference_day(message: Message, today: date) -> date:
    """
    От какого дня считать «завтра» и «к пятнице» в сообщении.

    Пересланное из чата класса написано раньше, чем переслано: «на завтра»,
    сказанное в пятницу и пересланное в субботу, — это суббота, а не
    воскресенье. Поэтому для пересланного берём дату оригинала.
    """
    origin = message.forward_origin
    if origin is None or origin.date is None:
        return today
    original = clock.local_date(origin.date)
    if original > today or (today - original).days > _MAX_FORWARD_AGE_DAYS:
        return today
    return original


def is_image_document(message: Message) -> bool:
    doc = message.document
    return bool(doc and (doc.mime_type or "").startswith("image/"))


def _to_jpeg(data: bytes) -> bytes:
    """Перекодирует изображение в JPEG, уменьшая слишком большие."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail((_MAX_SIDE, _MAX_SIDE))
            out = io.BytesIO()
            img.save(out, "JPEG", quality=90)
            return out.getvalue()
    except (UnidentifiedImageError, OSError) as e:
        raise UnsupportedImage(str(e)) from e


async def image_from_message(message: Message) -> ImageInput | None:
    """
    Изображение из сообщения: фото или картинка, отправленная файлом.
    None — в сообщении нет изображения. UnsupportedImage — есть, но не читается.
    """
    if message.photo:
        file_id, mime, size = message.photo[-1].file_id, "image/jpeg", message.photo[-1].file_size
    elif is_image_document(message):
        doc = message.document
        file_id, mime, size = doc.file_id, doc.mime_type or "", doc.file_size
    else:
        return None

    if size and size > MAX_IMAGE_BYTES:
        raise UnsupportedImage("файл больше 15 МБ")

    buffer = await message.bot.download(file_id, destination=io.BytesIO())
    data   = buffer.getvalue()

    if mime in _NATIVE_MIME and len(data) <= MAX_IMAGE_BYTES:
        return ImageInput(data=data, mime=mime)

    # webp, heic, gif и прочее — перекодируем в JPEG
    return ImageInput(data=await asyncio.to_thread(_to_jpeg, data), mime="image/jpeg")


class AlbumCollector:
    """
    Собирает сообщения одного альбома. Первое сообщение ждёт, пока
    подтянутся остальные, и получает всю пачку; остальные — None.
    """

    def __init__(self, delay: float = 1.2):
        self._delay  = delay
        self._groups: dict[str, list[Message]] = {}

    async def collect(self, message: Message) -> list[Message] | None:
        key   = message.media_group_id
        group = self._groups.setdefault(key, [])
        group.append(message)
        if len(group) > 1:
            return None

        await asyncio.sleep(self._delay)
        messages = self._groups.pop(key, group)
        return sorted(messages, key=lambda m: m.message_id)
