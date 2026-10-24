"""
Промпты и разбор ответов модели: расписание, замены уроков, домашние задания.

Какая модель отвечает — решает src/services/llm_providers.py. Здесь только
что спросить и как прочитать ответ. Ответы запрашиваются строго по
JSON-схеме, но модель всё равно может ошибиться в значениях, поэтому
каждое поле дополнительно проверяется кодом.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import Literal, Sequence

from src.core import clock
from src.services.llm_providers import ImageInput, get_router

logger = logging.getLogger(__name__)

_DAYS_RU       = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_DAYS_RU_FULL  = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_DAYS_RU_LOWER = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# Сколько дней вперёд показывать модели в календаре для перевода «на пятницу» в дату
_CALENDAR_DAYS = 14


class LLMBadResponse(ValueError):
    """Модель ответила, но ответ не удалось разобрать."""


def _today_ctx(today: date | None = None) -> str:
    today = today or clock.today()
    return f"{_DAYS_RU_FULL[today.weekday()]}, {today.strftime('%d.%m.%Y')}"


def _calendar(today: date) -> str:
    """Ближайшие дни с датами — модель хуже считает даты, чем читает их из списка."""
    lines = []
    for offset in range(_CALENDAR_DAYS):
        d = today + timedelta(days=offset)
        line = f"{_DAYS_RU_LOWER[d.weekday()]} {d.strftime('%d.%m')} → {d.isoformat()}"
        if offset == 0:
            line += " (сегодня)"
        elif offset == 1:
            line += " (завтра)"
        lines.append(line)
    return "\n".join(lines)


def _extract_json(raw: str) -> dict:
    """JSON-объект из ответа модели, даже если он обёрнут в markdown или текст."""
    text = raw.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise LLMBadResponse(f"Не удалось найти JSON в ответе: {raw[:200]}")
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        raise LLMBadResponse(f"Битый JSON в ответе: {raw[:200]}") from e


async def ask_text(prompt: str) -> str:
    """Однократный текстовый запрос к быстрой модели. Возвращает сырой ответ."""
    return await get_router().complete(prompt, tier="fast", max_tokens=300)


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

КАК НУМЕРОВАТЬ — САМОЕ ВАЖНОЕ:
Обрабатывай каждый день ОТДЕЛЬНО, строго сверху вниз по клеткам.
Первая непустая клетка дня = slot 1, следующая = slot 2, и так далее.
Просто считай по порядку, НЕ пытайся понять смысл предметов.

— Два одинаковых предмета подряд («АЛГЕБРА», «АЛГЕБРА») — это ДВА РАЗНЫХ
  урока с разными номерами (например slot 6 и slot 7). НЕ объединяй их.
— В одном дне НЕ МОЖЕТ быть двух записей с одинаковым slot, если это
  не подгруппы и не разные недели.
— Досчитывай день до конца: последняя клетка тоже урок, не пропускай её.
— В разных днях разное число уроков — это нормально.

Остальные правила:
— Расписание может быть таблицей: дни в столбцах или в строках. Определи ориентацию сам.
— Пустые клетки, окна и «нет урока» пропускай — не добавляй их в lessons.
— Время уроков игнорируй, нужен только порядковый номер.
— Классный час, факультатив, разговоры о важном — тоже уроки, включай их.

НАЗВАНИЯ ПРЕДМЕТОВ:
— Числа в скобках — это номер кабинета. Полностью убирай их:
  «РУССКИЙ(401)» → «Русский», «ФИЗИКА(202)» → «Физика».
— Раскрывай только очевидные сокращения: «матем.» → «Математика»,
  «физ-ра» → «Физкультура», «деят-ость» → «деятельность».
— НЕ ПРИДУМЫВАЙ расшифровки незнакомым словам. Если сокращение непонятное
  («ОБЗР», «ОДНКНР», «ИЗО»), оставь его КАК ЕСТЬ, заглавными.
— Приводи к виду «Первая буква заглавная»: «ОБЩЕСТВОЗНАНИЕ» → «Обществознание».

ПОДГРУППЫ. Если в одной клетке два предмета для разных частей класса
(«Англ. 1 гр. / Англ. 2 гр.», «Информатика (1) / Технология (2)»),
верни ДВЕ записи с одинаковыми day и slot, но subgroup 1 и 2.
Номер подгруппы убирай из названия предмета.
Если подгруппа не указана — ставь subgroup: 0.

ЧЁТНОСТЬ НЕДЕЛЬ. Ставь week_parity ТОЛЬКО если в клетке есть ЯВНАЯ
пометка чередования: слово числитель/знаменатель/чис./знам./верхняя/нижняя
или два предмета через дробь В ОДНОЙ клетке («Алгебра / Геометрия»).
Тогда верни ДВЕ записи с одинаковыми day и slot: первую с week_parity "odd",
вторую с "even". Пометку убирай из названия предмета.

Во ВСЕХ остальных случаях week_parity: "".
Два одинаковых предмета в СОСЕДНИХ клетках — это НЕ чередование,
а два обычных урока подряд. Ставь им week_parity: "" и разные slot.

confidence: насколько уверенно прочитано изображение (0.0–1.0).
Если на изображении нет расписания уроков, верни {"lessons":[],"confidence":0.0}\
"""


def _drop_false_parity(lessons: list[dict]) -> list[dict]:
    """
    Снимает пометку чередования недель там, где она бессмысленна.

    На реальных расписаниях модель принимает два одинаковых урока подряд
    («ГЕОМЕТРИЯ», «ГЕОМЕТРИЯ») за числитель и знаменатель. Но чередование
    между одним и тем же предметом ничего не значит: по обеим неделям идёт
    одно и то же. Такие пары — просто два урока подряд.
    """
    by_parity: dict[tuple[int, int, int], list[dict]] = {}
    by_subgroup: dict[tuple[int, int, str], list[dict]] = {}

    for lesson in lessons:
        if lesson["week_parity"]:
            by_parity.setdefault(
                (lesson["day"], lesson["slot"], lesson["subgroup"]), []
            ).append(lesson)
        if lesson["subgroup"]:
            by_subgroup.setdefault(
                (lesson["day"], lesson["slot"], lesson["week_parity"]), []
            ).append(lesson)

    def _same_subject(items: list[dict]) -> bool:
        return len({i["subject"].strip().lower() for i in items}) == 1

    for items in by_parity.values():
        if len(items) > 1 and _same_subject(items):
            for item in items:
                item["week_parity"] = ""

    # Одинаковый предмет «в обеих подгруппах» — тоже artefact распознавания:
    # делить класс, чтобы обе половины учили то же самое, незачем.
    for items in by_subgroup.values():
        if len(items) > 1 and _same_subject(items):
            for item in items:
                item["subgroup"] = 0

    return lessons


def _renumber_slots(lessons: list[dict]) -> list[dict]:
    """
    Перенумеровывает уроки внутри дня подряд, сохраняя порядок от модели.

    На реальных расписаниях модель сбивается со счёта, когда предмет
    повторяется: выдаёт два урока с одним номером. Раньше дубль молча
    отбрасывался, и урок терялся целиком. Здесь номер восстанавливается
    по позиции, а совпавшие подгруппы и чередующиеся недели сохраняют
    общий слот — они и должны его делить.
    """
    lessons = _drop_false_parity(lessons)

    by_day: dict[int, list[dict]] = {}
    for lesson in lessons:
        by_day.setdefault(lesson["day"], []).append(lesson)

    result: list[dict] = []
    for day in sorted(by_day):
        # Сортировка устойчива: при равном slot порядок от модели сохраняется
        items = sorted(by_day[day], key=lambda x: x["slot"])

        next_slot = 0
        # Слоты, уже выданные записям с подгруппой или чётностью:
        # исходный номер от модели → назначенный номер
        shared: dict[int, int] = {}

        for item in items:
            original = item["slot"]

            # Подгруппы и чередующиеся недели законно делят один слот
            if (item["subgroup"] or item["week_parity"]) and original in shared:
                item["slot"] = shared[original]
                result.append(item)
                continue

            next_slot += 1
            item["slot"] = next_slot
            if item["subgroup"] or item["week_parity"]:
                shared[original] = next_slot
            result.append(item)

    return result


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

        lessons.append({
            "day":         day,
            "slot":        slot,
            "subject":     subject,
            "subgroup":    subgroup,
            "week_parity": parity,
        })

    lessons = _renumber_slots(lessons)
    lessons.sort(key=lambda x: (x["day"], x["slot"], x["subgroup"], x["week_parity"]))

    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0

    return {"lessons": lessons, "confidence": max(0.0, min(1.0, confidence))}


_SCHEDULE_SCHEMA = {
    "type": "object",
    "properties": {
        "lessons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day":         {"type": "integer"},
                    "slot":        {"type": "integer"},
                    "subject":     {"type": "string"},
                    "subgroup":    {"type": "integer"},
                    "week_parity": {"type": "string"},
                },
                "required": ["day", "slot", "subject", "subgroup", "week_parity"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "number"},
    },
    "required": ["lessons", "confidence"],
    "additionalProperties": False,
}


async def parse_schedule_image(image: ImageInput) -> dict:
    """
    Распознаёт расписание на фото.
    Возвращает {"lessons": [{"day", "slot", "subject", ...}], "confidence": float}.
    Пустой список lessons означает, что расписание не распознано.
    """
    raw = await get_router().complete(
        _SCHEDULE_PROMPT, tier="smart", images=[image], schema=_SCHEDULE_SCHEMA, max_tokens=4000,
    )
    logger.debug("Schedule image raw: %s", raw)
    try:
        return _normalize_schedule(_extract_json(raw))
    except Exception:
        logger.warning("Не удалось разобрать расписание из ответа модели")
        return {"lessons": [], "confidence": 0.0}


async def parse_schedule_text(text: str) -> dict:
    """Распознаёт расписание из текстового сообщения в произвольном формате."""
    prompt = (
        "Ниже текст школьного расписания в произвольном формате.\n\n"
        + _SCHEDULE_PROMPT.replace("На изображении —", "В тексте —")
        + "\n\nТекст:\n"
        + text
    )
    raw = await get_router().complete(prompt, tier="smart", schema=_SCHEDULE_SCHEMA, max_tokens=4000)
    logger.debug("Schedule text raw: %s", raw)
    try:
        return _normalize_schedule(_extract_json(raw))
    except Exception:
        logger.warning("Не удалось разобрать расписание из текста")
        return {"lessons": [], "confidence": 0.0}


# ── Замены и отмены уроков ───────────────────────────────────────────────────

_OVERRIDE_RULES = """\
is_override: true — если сообщение объявляет замену или отмену урока, иначе false.
date:        конкретная дата YYYY-MM-DD. «Завтра», «в понедельник» — переведи по календарю.
slot:        номер урока, если указан явно («вместо 3 урока»). Иначе null.
old_subject: какой урок заменяют или отменяют. Иначе null.
new_subject: чем заменяют. При отмене — null.
cancelled:   true, если урок отменён и ничем не заменён.

ЭТО ЗАМЕНА:
✅ «Завтра вместо физики будет история»
✅ «Химии не будет в пятницу»
✅ «3 урок отменили»
✅ «В понедельник физру заменят на математику»

ЭТО НЕ ЗАМЕНА:
❌ «ДЗ по физике параграф 8» — домашнее задание
❌ «А что завтра по расписанию?» — вопрос
❌ «Физика была сложная» — обсуждение
❌ «Кто идёт на физру?» — вопрос\
"""

_OVERRIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_override": {"type": "boolean"},
        "date":        {"type": ["string", "null"]},
        "slot":        {"type": ["integer", "null"]},
        "old_subject": {"type": ["string", "null"]},
        "new_subject": {"type": ["string", "null"]},
        "cancelled":   {"type": "boolean"},
        "confidence":  {"type": "number"},
    },
    "required": ["is_override", "date", "slot", "old_subject", "new_subject", "cancelled", "confidence"],
    "additionalProperties": False,
}


async def detect_schedule_override(text: str, subjects: list[str]) -> dict | None:
    """
    Ищет в сообщении замену или отмену урока. Возвращает dict или None.

    Замены объявляют в том же чате, что и ДЗ, поэтому дешевле распознать их
    на лету, чем заставлять кого-то редактировать расписание вручную.
    """
    today  = clock.today()
    prompt = (
        "Ты определяешь, сообщает ли текст из школьного чата о замене или отмене урока.\n\n"
        "Сегодня: " + _today_ctx(today) + "\n"
        "Календарь:\n" + _calendar(today) + "\n\n"
        "Предметы класса: " + ", ".join(subjects) + "\n\n"
        + _OVERRIDE_RULES + "\n\n"
        "Сообщение:\n«" + text + "»"
    )
    raw = await get_router().complete(prompt, tier="fast", schema=_OVERRIDE_SCHEMA, max_tokens=300)
    logger.debug("Override detect raw: %s", raw)

    try:
        data = _extract_json(raw)
    except LLMBadResponse:
        logger.warning("Не удалось разобрать ответ о замене: %s", raw[:200])
        return None

    if not data.get("is_override") or not data.get("date"):
        return None
    return data


# ── Домашние задания ─────────────────────────────────────────────────────────

HomeworkSource = Literal["private", "chat"]

# Маркеры английского — ученики пишут сокращениями из учебника
_ENGLISH_MARKERS_HINT = """\
АНГЛИЙСКИЙ ЯЗЫК. Если в задании есть ex., exercise, p., pg., page, H/W, HW,
W/B, WB, S/B, SB, Unit, Vocabulary — это «Английский язык» (если он есть
в расписании). Исключение: только цифры и формулы без английских слов —
это математика.\
"""

_HOMEWORK_RULES = """\
ПРАВИЛА
1. Найди ВСЕ домашние задания. Одно задание — один предмет: несколько пунктов
   по одному предмету объединяй в одно задание через запятую.
2. subject — название из списка предметов, если оно подходит
   («Англ.», «англ яз» → «Английский язык»; «алгебра» → «Алгебра»).
   Если предмета нет в списке — полное название, как в источнике.
3. task — что сделать: кратко, но со ВСЕМИ номерами, страницами, параграфами,
   упражнениями. Без слов «ДЗ», «задали» и без названия предмета.
4. due_date — к какой дате сделать, в формате YYYY-MM-DD по календарю выше.
   Ставь, только если срок указан явно: «на пятницу», «к 15.11», «на завтра»,
   «к понедельнику». Срок не указан или «к следующему уроку» → null.
5. Страница бумажного дневника или скриншот электронного: задание записано
   в строке того дня, НА КОТОРЫЙ его задали. Дата или день недели этой строки
   и есть due_date.
6. confidence — насколько уверенно прочитано задание, от 0.0 до 1.0.
   Неразборчивый почерк, обрезанный текст, догадка → меньше 0.6.
7. Ничего не выдумывай. Нет домашнего задания — пустой список items.\
"""

_CHAT_EXAMPLES = """\
Это сообщение из общего чата класса — там в основном переписка.

ЭТО ДОМАШНЕЕ ЗАДАНИЕ:
✅ «ДЗ по физике: §8 задачи 1-3»
✅ «На пятницу выучить стихотворение (литература)»
✅ «Математика — стр.45 упр.7, сдать в четверг»
✅ «Не забудьте параграф 12 прочитать к завтрашнему уроку химии»

ЭТО НЕ ДОМАШНЕЕ ЗАДАНИЕ (items пустой):
❌ «Кто сделал домашку по математике?» — вопрос
❌ «Завтра контрольная по физике» — объявление
❌ «Привет всем!», «Спасибо за помощь» — переписка
❌ «Молодцы, все справились» — комментарий\
"""

_HOMEWORK_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject":    {"type": "string"},
                    "task":       {"type": "string"},
                    "due_date":   {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["subject", "task", "due_date", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}


def build_homework_prompt(
    text: str,
    image_count: int,
    subjects: Sequence[str],
    today: date,
    source: HomeworkSource,
) -> str:
    """Промпт разбора ДЗ. Строится конкатенацией — безопасно для любого текста."""
    if subjects:
        subjects_line = "Предметы в расписании: " + ", ".join(subjects)
    else:
        subjects_line = "Расписание не задано — пиши предмет полным названием, как в источнике."

    if source == "chat":
        intro = _CHAT_EXAMPLES
    else:
        intro = (
            "Ученик прислал своё домашнее задание: текст и/или фото — дневник, доска, "
            "тетрадь, учебник, скриншот из чата или электронного дневника."
        )

    if text.strip():
        material = "Текст сообщения:\n«" + text.strip() + "»"
    else:
        material = "Текста нет — только фото."
    if image_count:
        material += f"\nФото в сообщении: {image_count} (они выше)."

    return (
        "Ты помогаешь школьнику вести домашние задания.\n\n"
        "Сегодня: " + _today_ctx(today) + "\n"
        "Календарь (день → дата для due_date):\n" + _calendar(today) + "\n\n"
        + subjects_line + "\n\n"
        + intro + "\n\n"
        + _HOMEWORK_RULES + "\n\n"
        + _ENGLISH_MARKERS_HINT + "\n\n"
        + material
    )


def normalize_homework(data: dict) -> list[dict]:
    """
    Приводит ответ модели к списку {"subject", "task", "due_date", "confidence"}.
    Записи без текста задания отбрасываются; due_date остаётся сырой строкой —
    её проверяет и переводит в дату код, а не модель.
    """
    items = data.get("items")
    if not isinstance(items, list):
        return []

    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        task    = str(item.get("task") or "").strip()
        subject = str(item.get("subject") or "").strip()
        if not task:
            continue

        due = item.get("due_date")
        due = str(due).strip() if due not in (None, "", "null") else None

        try:
            confidence = float(item.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7

        result.append({
            "subject":    subject,
            "task":       task,
            "due_date":   due,
            "confidence": max(0.0, min(1.0, confidence)),
        })
    return result


async def extract_homework(
    *,
    text: str = "",
    images: Sequence[ImageInput] = (),
    subjects: Sequence[str] = (),
    today: date | None = None,
    source: HomeworkSource = "private",
) -> list[dict]:
    """
    Все домашние задания из сообщения: текста и любого числа фото.

    Личные ДЗ разбирает самая точная модель. В чате класса сообщений много,
    поэтому текст идёт в быструю модель, фото — в модель со зрением попроще.

    Бросает LLMUnavailable, если модели недоступны, и LLMBadResponse,
    если ответ не разобрать, — вызывающий должен сказать об этом человеку,
    а не делать вид, что заданий нет.
    """
    today  = today or clock.today()
    prompt = build_homework_prompt(text, len(images), subjects, today, source)

    if source == "private":
        tier = "smart"
    else:
        tier = "vision" if images else "fast"

    raw = await get_router().complete(
        prompt, tier=tier, images=images, schema=_HOMEWORK_SCHEMA, max_tokens=2000,
    )
    logger.debug("Homework raw (%s): %s", source, raw)
    return normalize_homework(_extract_json(raw))
