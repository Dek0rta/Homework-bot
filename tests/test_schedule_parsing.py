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
    result = _normalize_schedule({
        "lessons": [
            {"day": 2, "slot": 1, "subject": "Химия"},
            {"day": 0, "slot": 3, "subject": "Физика"},
            {"day": 0, "slot": 1, "subject": "Математика"},
        ],
        "confidence": 0.8,
    })
    assert [(l["day"], l["slot"]) for l in result["lessons"]] == [(0, 1), (0, 3), (2, 1)]


def test_duplicate_slots_are_dropped():
    """Один слот не может содержать два предмета — берём первый."""
    result = _normalize_schedule({
        "lessons": [
            {"day": 0, "slot": 1, "subject": "Математика"},
            {"day": 0, "slot": 1, "subject": "Физика"},
        ],
        "confidence": 0.7,
    })
    assert len(result["lessons"]) == 1
    assert result["lessons"][0]["subject"] == "Математика"


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
