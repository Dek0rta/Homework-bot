"""
Чётность учебных недель («числитель / знаменатель»).

В школах расписание часто различается по неделям: на одном и том же уроке
в нечётную неделю алгебра, в чётную — геометрия. Названия у этого разные —
числитель/знаменатель, верхняя/нижняя, первая/вторая — но смысл один:
двухнедельный цикл.

Опорная дата (anchor) — понедельник недели, которую класс считает нечётной.
Всё остальное считается от неё, поэтому класс может сдвинуть отсчёт одной
командой, если ошибся, не трогая само расписание.
"""

from __future__ import annotations

from datetime import date, timedelta

# Значения поля week_parity в class_schedule
PARITY_EVERY = ""      # урок каждую неделю
PARITY_ODD   = "odd"   # нечётная неделя (числитель)
PARITY_EVEN  = "even"  # чётная неделя (знаменатель)

VALID_PARITIES = (PARITY_EVERY, PARITY_ODD, PARITY_EVEN)

# Как это называют в расписаниях — для распознавания и вывода
PARITY_LABELS = {
    PARITY_EVERY: "каждую неделю",
    PARITY_ODD:   "числитель",
    PARITY_EVEN:  "знаменатель",
}

# Синонимы из реальных расписаний → каноническое значение
_PARITY_SYNONYMS = {
    "числитель": PARITY_ODD,
    "чис": PARITY_ODD,
    "нечет": PARITY_ODD,
    "нечёт": PARITY_ODD,
    "нечетная": PARITY_ODD,
    "нечётная": PARITY_ODD,
    "верхняя": PARITY_ODD,
    "первая": PARITY_ODD,
    "odd": PARITY_ODD,
    "1": PARITY_ODD,

    "знаменатель": PARITY_EVEN,
    "знам": PARITY_EVEN,
    "чет": PARITY_EVEN,
    "чёт": PARITY_EVEN,
    "четная": PARITY_EVEN,
    "чётная": PARITY_EVEN,
    "нижняя": PARITY_EVEN,
    "вторая": PARITY_EVEN,
    "even": PARITY_EVEN,
    "2": PARITY_EVEN,
}


def normalize_parity(raw: str | None) -> str:
    """Приводит произвольное обозначение чётности к каноническому виду."""
    if not raw:
        return PARITY_EVERY
    key = str(raw).strip().lower().rstrip(".")
    if key in VALID_PARITIES:
        return key
    return _PARITY_SYNONYMS.get(key, PARITY_EVERY)


def monday_of(day: date) -> date:
    """Понедельник недели, которой принадлежит дата."""
    return day - timedelta(days=day.weekday())


def week_parity(day: date, anchor: date | None) -> str:
    """
    Чётность недели, которой принадлежит day.

    anchor — понедельник недели, объявленной нечётной. Без него отсчёт вести
    не от чего, поэтому возвращается PARITY_EVERY: расписание показывается
    целиком, и класс ничего не теряет.
    """
    if anchor is None:
        return PARITY_EVERY

    weeks_apart = (monday_of(day) - monday_of(anchor)).days // 7
    return PARITY_ODD if weeks_apart % 2 == 0 else PARITY_EVEN


def lesson_happens_on(lesson_parity: str, day: date, anchor: date | None) -> bool:
    """
    Проводится ли урок в этот день.

    Урок без указанной чётности идёт всегда. Если опорная дата не задана,
    показываем все уроки — лучше лишний, чем потерянный.
    """
    parity = normalize_parity(lesson_parity)
    if parity == PARITY_EVERY:
        return True
    if anchor is None:
        return True
    return parity == week_parity(day, anchor)


def parity_suffix(lesson_parity: str) -> str:
    """Пометка чётности для вывода. Пустая строка для еженедельных уроков."""
    parity = normalize_parity(lesson_parity)
    return "" if parity == PARITY_EVERY else f" ({PARITY_LABELS[parity]})"
