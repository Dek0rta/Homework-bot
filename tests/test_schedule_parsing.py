"""
Тесты нормализации распознанного расписания.

Модель возвращает свободный JSON, поэтому важно, что мусор отсеивается,
а не попадает в расписание класса.
"""

from __future__ import annotations

from src.services.llm import _normalize_schedule


def test_valid_schedule_passes_through():
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": "Математика"},
            {"day": 0, "slot": 2, "subject": "Физика"},
        ],
        "confidence": 0.9,
    })
    assert len(result["lessons"]) == 2
    assert result["confidence"] == 0.9


def test_lessons_are_sorted_by_day_and_slot():
    """
    Порядок восстанавливается по дню и номеру. Пропуск в нумерации от
    модели схлопывается: уроки идут подряд, окна в расписании не хранятся.
    """
    result = _normalize_schedule({
        "lessons": [
            {"day": 2, "slot": 1, "subject": "Химия"},
            {"day": 0, "slot": 3, "subject": "Физика"},
            {"day": 0, "slot": 1, "subject": "Математика"},
        ],
        "confidence": 0.8,
    })
    assert [(l["day"], l["slot"]) for l in result["lessons"]] == [(0, 1), (0, 2), (2, 1)]
    assert [l["subject"] for l in result["lessons"]] == ["Математика", "Физика", "Химия"]


def test_duplicate_slots_are_renumbered_not_dropped():
    """
    Регрессия на реальном расписании: модель сбивается со счёта при
    повторяющихся предметах и выдаёт два урока с одним номером. Раньше
    дубль отбрасывался и урок терялся; теперь номер восстанавливается.
    """
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": "Математика"},
            {"day": 0, "slot": 1, "subject": "Физика"},
        ],
        "confidence": 0.7,
    })
    assert len(result["lessons"]) == 2
    assert [l["slot"] for l in result["lessons"]] == [1, 2]
    assert [l["subject"] for l in result["lessons"]] == ["Математика", "Физика"]


def test_real_schedule_keeps_every_lesson():
    """
    Вторник с реального фото: модель выдала «3. История» и «3. Алгебра»,
    из-за чего терялся последний урок дня. Все 8 должны сохраниться.
    """
    raw = [
        {"day": 1, "slot": 1, "subject": "Русский"},
        {"day": 1, "slot": 2, "subject": "Литература"},
        {"day": 1, "slot": 3, "subject": "История"},
        {"day": 1, "slot": 3, "subject": "Алгебра"},
        {"day": 1, "slot": 4, "subject": "Обществознание"},
        {"day": 1, "slot": 5, "subject": "Химия"},
        {"day": 1, "slot": 6, "subject": "Алгебра"},
        {"day": 1, "slot": 7, "subject": "Алгебра"},
    ]
    result = _normalize_schedule({"lessons": raw, "confidence": 0.8})

    assert len(result["lessons"]) == 8
    assert [l["slot"] for l in result["lessons"]] == [1, 2, 3, 4, 5, 6, 7, 8]


def test_repeated_subject_stays_two_lessons():
    """«Алгебра, Алгебра» подряд — два разных урока, а не один."""
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 6, "subject": "Алгебра"},
            {"day": 0, "slot": 7, "subject": "Алгебра"},
        ],
        "confidence": 0.9,
    })
    assert len(result["lessons"]) == 2


def test_renumbering_is_per_day():
    """Нумерация начинается заново каждый день."""
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": "A"},
            {"day": 0, "slot": 1, "subject": "B"},
            {"day": 1, "slot": 1, "subject": "C"},
        ],
        "confidence": 0.8,
    })
    by_day = {}
    for lesson in result["lessons"]:
        by_day.setdefault(lesson["day"], []).append(lesson["slot"])

    assert by_day[0] == [1, 2]
    assert by_day[1] == [1]


def test_subgroups_still_share_one_slot():
    """
    Подгруппы законно делят слот — перенумерация не должна их разводить.
    Предметы разные: одинаковые считаются артефактом распознавания.
    """
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": "Английский",  "subgroup": 1},
            {"day": 0, "slot": 1, "subject": "Информатика", "subgroup": 2},
            {"day": 0, "slot": 2, "subject": "Математика"},
        ],
        "confidence": 0.9,
    })
    slots = {(l["subject"], l["subgroup"]): l["slot"] for l in result["lessons"]}
    assert slots[("Английский", 1)] == slots[("Информатика", 2)] == 1
    assert slots[("Математика", 0)] == 2


def test_same_subject_twice_is_not_alternating_weeks():
    """
    Регрессия на реальном фото: две «Геометрии» подряд модель приняла за
    числитель и знаменатель. Чередование между одним и тем же предметом
    бессмысленно — это два обычных урока.
    """
    result = _normalize_schedule({
        "lessons": [
            {"day": 2, "slot": 1, "subject": "Физкультура"},
            {"day": 2, "slot": 2, "subject": "Геометрия", "week_parity": "odd"},
            {"day": 2, "slot": 2, "subject": "Геометрия", "week_parity": "even"},
            {"day": 2, "slot": 3, "subject": "Химия"},
        ],
        "confidence": 0.9,
    })
    assert [l["slot"] for l in result["lessons"]] == [1, 2, 3, 4]
    assert all(l["week_parity"] == "" for l in result["lessons"])


def test_same_subject_in_both_subgroups_is_not_a_split():
    """Делить класс, чтобы обе половины учили то же самое, незачем."""
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": "Алгебра", "subgroup": 1},
            {"day": 0, "slot": 1, "subject": "Алгебра", "subgroup": 2},
        ],
        "confidence": 0.9,
    })
    assert [l["slot"] for l in result["lessons"]] == [1, 2]
    assert all(l["subgroup"] == 0 for l in result["lessons"])


def test_genuine_alternating_weeks_preserved():
    """Настоящее чередование — разные предметы — сохраняется."""
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": "Алгебра",   "week_parity": "odd"},
            {"day": 0, "slot": 1, "subject": "Геометрия", "week_parity": "even"},
        ],
        "confidence": 0.9,
    })
    assert {l["slot"] for l in result["lessons"]} == {1}
    assert {l["week_parity"] for l in result["lessons"]} == {"odd", "even"}


def test_genuine_subgroups_preserved():
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": "Английский",  "subgroup": 1},
            {"day": 0, "slot": 1, "subject": "Информатика", "subgroup": 2},
        ],
        "confidence": 0.9,
    })
    assert {l["slot"] for l in result["lessons"]} == {1}
    assert {l["subgroup"] for l in result["lessons"]} == {1, 2}


def test_alternating_weeks_still_share_one_slot():
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": "Алгебра",   "week_parity": "odd"},
            {"day": 0, "slot": 1, "subject": "Геометрия", "week_parity": "even"},
            {"day": 0, "slot": 2, "subject": "История"},
        ],
        "confidence": 0.9,
    })
    slots = {l["subject"]: l["slot"] for l in result["lessons"]}
    assert slots["Алгебра"] == slots["Геометрия"] == 1
    assert slots["История"] == 2


def test_empty_subject_is_dropped():
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": ""},
            {"day": 0, "slot": 2, "subject": "   "},
            {"day": 0, "slot": 3, "subject": "Физика"},
        ],
        "confidence": 0.8,
    })
    assert len(result["lessons"]) == 1


def test_out_of_range_values_are_dropped():
    result = _normalize_schedule({
        "lessons": [
            {"day": 9,  "slot": 1, "subject": "Несуществующий день"},
            {"day": -1, "slot": 1, "subject": "Отрицательный день"},
            {"day": 0,  "slot": 0, "subject": "Нулевой урок"},
            {"day": 0,  "slot": 99, "subject": "Урок вне сетки"},
            {"day": 0,  "slot": 1, "subject": "Нормальный"},
        ],
        "confidence": 0.8,
    })
    assert len(result["lessons"]) == 1
    assert result["lessons"][0]["subject"] == "Нормальный"


def test_malformed_entries_do_not_crash():
    result = _normalize_schedule({
        "lessons": [
            {"day": "не число", "slot": 1, "subject": "X"},
            {"slot": 1, "subject": "нет дня"},
            {"day": 0, "subject": "нет слота"},
            None,
            "строка вместо объекта",
            {"day": 1, "slot": 2, "subject": "Валидный"},
        ],
        "confidence": 0.6,
    })
    assert len(result["lessons"]) == 1
    assert result["lessons"][0]["subject"] == "Валидный"


def test_missing_lessons_key_gives_empty():
    assert _normalize_schedule({})["lessons"] == []
    assert _normalize_schedule({"lessons": None})["lessons"] == []


def test_confidence_is_clamped():
    assert _normalize_schedule({"lessons": [], "confidence": 5})["confidence"] == 1.0
    assert _normalize_schedule({"lessons": [], "confidence": -2})["confidence"] == 0.0
    assert _normalize_schedule({"lessons": [], "confidence": "мусор"})["confidence"] == 0.0


def test_subject_whitespace_is_trimmed():
    result = _normalize_schedule({
        "lessons": [{"day": 0, "slot": 1, "subject": "  Математика  "}],
        "confidence": 0.9,
    })
    assert result["lessons"][0]["subject"] == "Математика"
