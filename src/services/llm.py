"""
Разбор домашних заданий через Mistral: текст (mistral-small) и фото (Pixtral).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from datetime import datetime

from mistralai import Mistral

from src.core.config import MISTRAL_API_KEY

logger = logging.getLogger(__name__)

_client = Mistral(api_key=MISTRAL_API_KEY)

_TEXT_MODEL   = "mistral-small-latest"
_VISION_MODEL = "pixtral-12b-2409"

_DAYS_RU      = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_DAYS_RU_FULL = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]


def _today_ctx() -> str:
    now = datetime.now()
    return f"{_DAYS_RU_FULL[now.weekday()]}, {now.strftime('%d.%m.%Y')}"


_GROUP_JSON_HINT = """\
Ответь СТРОГО одним из двух вариантов (без markdown, без пояснений):
— Если ДЗ: {"subject":"...","task":"...","due_day":<0-6 или null>,"due_date":"<YYYY-MM-DD или null>","confidence":<0.0-1.0>}
— Если НЕ ДЗ: null

due_day: день недели из текста (0=Пн…6=Вс), null если не указан явно
due_date: конкретная дата из текста в формате YYYY-MM-DD, null если не указана
confidence: твоя уверенность в правильности определения предмета (0.0–1.0)\
"""

_GROUP_EXAMPLES = """\
ПРИМЕРЫ — ЧТО ЯВЛЯЕТСЯ ДЗ:
✅ «ДЗ по физике: §8 задачи 1-3»
✅ «На пятницу выучить стихотворение (литература)»
✅ «Математика — стр.45 упр.7, сдать в четверг»
✅ «Не забудьте параграф 12 прочитать к завтрашнему уроку химии»

ПРИМЕРЫ — ЧТО НЕ ЯВЛЯЕТСЯ ДЗ:
❌ «Кто сделал домашку по математике?» — вопрос, не задание
❌ «Завтра контрольная по физике» — объявление, не ДЗ
❌ «Привет всем!» — переписка
❌ «Спасибо за помощь» — переписка
❌ «Кто придет на дополнительное занятие?» — вопрос
❌ «Молодцы, все справились» — комментарий\
"""

_JSON_HINT = (
    'Ответь СТРОГО в виде JSON-объекта без markdown-блоков:\n'
    '{"subject": "...", "task": "...", "due_lesson_day": <0-6>, "due_lesson_time": "ЧЧ:ММ", "confidence": <0.0-1.0>}\n\n'
    "due_lesson_day: 0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Вс\n"
    "confidence: уверенность в правильности определения предмета (0.0–1.0)"
)

# Маркеры Английского языка — включаются в каждый промпт распознавания ДЗ
_ENGLISH_MARKERS_HINT = """\
ПРИОРИТЕТНОЕ ПРАВИЛО — «Английский язык»:
Если в тексте или на изображении обнаружен хотя бы один из следующих маркеров,
классифицируй предмет как «Английский язык» (если он есть в расписании):
  • ex. / Ex. / exercise  — обозначение упражнения
  • p. / pg. / page        — ссылка на страницу учебника
  • H/W / HW               — аббревиатура Homework
  • W/B / WB               — Workbook (рабочая тетрадь)
  • S/B / SB               — Student's Book
  • Unit / unit            — раздел англоязычного учебника
  • Vocabulary / vocab     — словарный запас

Исключение (Английский vs Математика):
Если одновременно есть маркеры p./ex. И математические формулы:
  — Основной текст на английском языке → «Английский язык»
  — Только цифры и математические символы без английских слов → «Математика»/«Алгебра»/«Геометрия»\
"""


def _format_schedule(schedule: list[dict]) -> str:
    lines = []
    for e in schedule:
        day_name = _DAYS_RU[e["day_of_week"]]
        lines.append(f"{day_name}: {e['subject']} {e['start_time']}")
    return "\n".join(lines)


def _extract_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Не удалось найти JSON в ответе: {raw[:200]}")
    return json.loads(match.group())


async def _chat(messages: list[dict], model: str, max_retries: int = 4) -> str:
    """Отправляет запрос к Mistral с повтором при ошибке 429."""
    for attempt in range(max_retries):
        try:
            response = await _client.chat.complete_async(
                model=model,
                messages=messages,
                temperature=0.1,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("Mistral 429, повтор через %ds (попытка %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
            else:
                raise


async def ask_text(prompt: str) -> str:
    """Публичный однократный текстовый запрос к LLM. Возвращает сырой ответ модели."""
    return await _chat([{"role": "user", "content": prompt}], _TEXT_MODEL)


# ── Распознавание расписания ─────────────────────────────────────────────────

_SCHEDULE_PROMPT = """\
На изображении — школьное расписание уроков. Распознай его целиком.

Верни СТРОГО JSON без markdown:
{"lessons":[{"day":<0-6>,"slot":<1-8>,"subject":"...","subgroup":<0-9>,"week_parity":"<''|odd|even>"}],"confidence":<0.0-1.0>}

day:      0=Понедельник, 1=Вторник, 2=Среда, 3=Четверг, 4=Пятница, 5=Суббота
slot:     порядковый номер урока в этот день, начиная с 1
subject:  название предмета как написано, но в читаемом виде
          («матем.» → «Математика», «физ-ра» → «Физкультура»)
subgroup: 0 — урок у всего класса (обычный случай)
          1, 2 — если урок только для части класса
week_parity: "" — урок каждую неделю (обычный случай)
             "odd"  — числитель / нечётная / верхняя / первая неделя
             "even" — знаменатель / чётная / нижняя / вторая неделя

Правила:
— Расписание может быть таблицей: дни в столбцах или в строках. Определи ориентацию сам.
— Пустые клетки, окна и «нет урока» пропускай — не добавляй их в lessons.
— Если номера уроков не подписаны, нумеруй сверху вниз в пределах дня.
— Время уроков игнорируй, нужен только порядковый номер.
— Классный час, факультатив и подобное — тоже уроки, включай их.

ПОДГРУППЫ. Если в одной клетке два предмета для разных частей класса
(«Англ. 1 гр. / Англ. 2 гр.», «Информатика (1) / Технология (2)»),
верни ДВЕ записи с одинаковыми day и slot, но subgroup 1 и 2.
Номер подгруппы убирай из названия предмета.
Если подгруппа не указана — ставь subgroup: 0.

ЧЁТНОСТЬ НЕДЕЛЬ. Если в клетке предмет через дробь или с пометкой
числитель/знаменатель («Алгебра / Геометрия», «Химия (чис.)»),
верни ДВЕ записи с одинаковыми day и slot: первую с week_parity "odd",
вторую с "even". Пометку убирай из названия предмета.
Если пометки нет — ставь week_parity: "".

confidence: насколько уверенно прочитано изображение (0.0–1.0).
Если на изображении нет расписания уроков, верни {"lessons":[],"confidence":0.0}\
"""


def _normalize_schedule(data: dict) -> dict:
    """
    Приводит ответ модели к безопасному виду: отбрасывает мусорные записи,
    убирает дубли и сортирует.

    Уникальность — по (день, урок, подгруппа, чётность): один слот законно
    содержит несколько записей, если это разные подгруппы или разные недели.
    """
    from src.services.weeks import normalize_parity

    seen: set[tuple[int, int, int, str]] = set()
    lessons = []

    for item in data.get("lessons") or []:
        try:
            day     = int(item["day"])
            slot    = int(item["slot"])
            subject = str(item.get("subject", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue

        if not subject or not (0 <= day <= 6) or not (1 <= slot <= 8):
            continue

        try:
            subgroup = int(item.get("subgroup", 0) or 0)
        except (TypeError, ValueError):
            subgroup = 0
        if not (0 <= subgroup <= 9):
            subgroup = 0

        parity = normalize_parity(item.get("week_parity"))

        key = (day, slot, subgroup, parity)
        if key in seen:
            continue

        seen.add(key)
        lessons.append({
            "day":         day,
            "slot":        slot,
            "subject":     subject,
            "subgroup":    subgroup,
            "week_parity": parity,
        })

    lessons.sort(key=lambda x: (x["day"], x["slot"], x["subgroup"], x["week_parity"]))

    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0

    return {"lessons": lessons, "confidence": max(0.0, min(1.0, confidence))}


async def parse_schedule_image(image_path: str) -> dict:
    """
    Распознаёт расписание на фото.
    Возвращает {"lessons": [{"day", "slot", "subject"}], "confidence": float}.
    Пустой список lessons означает, что расписание не распознано.
    """
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    messages = [{
        "role": "user",
        "content": [
            {"type": "text",      "text": _SCHEDULE_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ],
    }]

    raw = await _chat(messages, _VISION_MODEL)
    logger.debug("Schedule image raw: %s", raw)
    try:
        return _normalize_schedule(_extract_json(raw))
    except Exception:
        logger.warning("Не удалось разобрать расписание из ответа модели")
        return {"lessons": [], "confidence": 0.0}


_OVERRIDE_HINT = """\
Ответь СТРОГО одним из двух вариантов, без markdown:
— Если это замена или отмена урока:
  {"date":"<YYYY-MM-DD>","slot":<1-8 или null>,"old_subject":"<или null>","new_subject":"<или null>","cancelled":<true|false>,"confidence":<0.0-1.0>}
— Если сообщение не про замену: null

date:        конкретная дата. «завтра», «в понедельник» — переведи в дату.
slot:        номер урока, если указан явно («вместо 3 урока»). Иначе null.
old_subject: какой урок заменяют или отменяют. Иначе null.
new_subject: чем заменяют. При отмене — null.
cancelled:   true если урок отменён/его не будет, без замены другим.\
"""

_OVERRIDE_EXAMPLES = """\
ПРИМЕРЫ — ЭТО ЗАМЕНА:
✅ «Завтра вместо физики будет история»
✅ «Химии не будет в пятницу»
✅ «3 урок отменили»
✅ «В понедельник физру заменят на математику»

ПРИМЕРЫ — ЭТО НЕ ЗАМЕНА:
❌ «ДЗ по физике параграф 8» — домашнее задание
❌ «А что завтра по расписанию?» — вопрос
❌ «Физика была сложная» — обсуждение
❌ «Кто идёт на физру?» — вопрос\
"""


async def detect_schedule_override(text: str, subjects: list[str]) -> dict | None:
    """
    Ищет в сообщении замену или отмену урока. Возвращает dict или None.

    Замены объявляют в том же чате, что и ДЗ, поэтому дешевле распознать их
    на лету, чем заставлять кого-то редактировать расписание вручную.
    """
    prompt = (
        "Ты определяешь, сообщает ли текст о замене или отмене урока.\n\n"
        "Сегодня: " + _today_ctx() + "\n"
        "Предметы класса: " + ", ".join(subjects) + "\n\n"
        + _OVERRIDE_EXAMPLES + "\n\n"
        "Сообщение:\n«" + text + "»\n\n"
        + _OVERRIDE_HINT
    )
    raw = await _chat([{"role": "user", "content": prompt}], _TEXT_MODEL)
    logger.debug("Override detect raw: %s", raw)

    result = _parse_group_result(raw)
    if not result or not result.get("date"):
        return None
    return result


async def parse_schedule_text(text: str) -> dict:
    """Распознаёт расписание из текстового сообщения в произвольном формате."""
    prompt = (
        "Ниже текст школьного расписания в произвольном формате.\n\n"
        + _SCHEDULE_PROMPT.replace("На изображении —", "В тексте —")
        + "\n\nТекст:\n"
        + text
    )
    raw = await _chat([{"role": "user", "content": prompt}], _TEXT_MODEL)
    logger.debug("Schedule text raw: %s", raw)
    try:
        return _normalize_schedule(_extract_json(raw))
    except Exception:
        logger.warning("Не удалось разобрать расписание из текста")
        return {"lessons": [], "confidence": 0.0}


async def parse_homework_text(text: str, schedule: list[dict]) -> dict:
    """Парсит ДЗ из текста. Промпт строится конкатенацией — безопасно для любого текста."""
    prompt = (
        "Ты помощник школьника. Тебе дан текст с домашним заданием и расписание уроков.\n\n"
        "Расписание (формат «День: Предмет ЧЧ:ММ»):\n"
        + _format_schedule(schedule)
        + "\n\n"
        + _ENGLISH_MARKERS_HINT
        + "\n\nТекст домашнего задания:\n"
        + text
        + "\n\nЗадача:\n"
        "1. Определи предмет из расписания (subject). Обяза­тельно применяй правила выше для маркеров Английского.\n"
        "2. Извлеки краткое описание задания (task).\n"
        "3. Найди ближайший следующий урок по этому предмету (due_lesson_day, due_lesson_time).\n"
        "4. Укажи confidence — твою уверенность в предмете.\n\n"
        + _JSON_HINT
    )
    raw = await _chat([{"role": "user", "content": prompt}], _TEXT_MODEL)
    logger.debug("Mistral raw: %s", raw)
    return _extract_json(raw)


def _parse_group_result(raw: str) -> dict | None:
    """null → None, JSON → dict с нормализованными полями."""
    raw = raw.strip()
    if raw.lower() in ("null", "none", ""):
        return None
    try:
        data = _extract_json(raw)
        if str(data.get("due_day",  "")).lower() == "null": data["due_day"]  = None
        if str(data.get("due_date", "")).lower() == "null": data["due_date"] = None
        return data
    except Exception:
        return None


async def detect_group_homework(text: str, subjects: list[str]) -> dict | None:
    """Определяет ДЗ в тексте группового чата. Возвращает dict или None."""
    prompt = (
        "Ты определяешь, является ли сообщение из школьного чата домашним заданием.\n\n"
        "Сегодня: " + _today_ctx() + "\n"
        "Предметы класса: " + ", ".join(subjects) + "\n\n"
        + _ENGLISH_MARKERS_HINT + "\n\n"
        + _GROUP_EXAMPLES + "\n\n"
        "Сообщение для анализа:\n«" + text + "»\n\n"
        + _GROUP_JSON_HINT
    )
    raw = await _chat([{"role": "user", "content": prompt}], _TEXT_MODEL)
    logger.debug("Group detect raw: %s", raw)
    return _parse_group_result(raw)


async def detect_group_homework_image(image_path: str, subjects: list[str]) -> dict | None:
    """Определяет ДЗ на фото из группы. Возвращает dict или None."""
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    prompt = (
        "Ты определяешь, содержит ли изображение домашнее задание из школы.\n\n"
        "Сегодня: " + _today_ctx() + "\n"
        "Предметы класса: " + ", ".join(subjects) + "\n\n"
        + _ENGLISH_MARKERS_HINT + "\n\n"
        "Прочитай весь текст на изображении. "
        "Это домашнее задание по одному из предметов?\n\n"
        + _GROUP_JSON_HINT
    )
    messages = [{
        "role": "user",
        "content": [
            {"type": "text",      "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ],
    }]
    raw = await _chat(messages, _VISION_MODEL)
    logger.debug("Group image detect raw: %s", raw)
    return _parse_group_result(raw)


async def parse_homework_image(image_path: str, schedule: list[dict]) -> dict:
    """Читает изображение и парсит ДЗ."""
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    prompt = (
        "Ты помощник школьника. На изображении записано домашнее задание.\n\n"
        "Расписание уроков (формат «День: Предмет ЧЧ:ММ»):\n"
        + _format_schedule(schedule)
        + "\n\n"
        + _ENGLISH_MARKERS_HINT
        + "\n\nЗадача:\n"
        "1. Прочитай весь текст на изображении.\n"
        "2. Определи предмет из расписания (subject). Обяза­тельно применяй правила выше для маркеров Английского.\n"
        "3. Извлеки краткое описание задания (task).\n"
        "4. Найди ближайший следующий урок по этому предмету (due_lesson_day, due_lesson_time).\n"
        "5. Укажи confidence — твою уверенность в предмете.\n\n"
        + _JSON_HINT
    )

    messages = [{
        "role": "user",
        "content": [
            {"type": "text",      "text": prompt},
            # image_url должен быть dict с ключом url (Mistral API v1+)
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ],
    }]

    raw = await _chat(messages, _VISION_MODEL)
    logger.debug("Mistral raw: %s", raw)
    return _extract_json(raw)
