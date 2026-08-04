"""Тесты чётности учебных недель."""

from __future__ import annotations

from datetime import date, timedelta

from src.services.weeks import (
    PARITY_EVEN,
    PARITY_EVERY,
    PARITY_ODD,
    lesson_happens_on,
    monday_of,
    normalize_parity,
    parity_suffix,
    week_parity,
)

# Понедельник — опорная нечётная неделя
ANCHOR = date(2026, 9, 7)


def test_monday_of_finds_week_start():
    assert monday_of(date(2026, 9, 9)) == date(2026, 9, 7)   # среда
    assert monday_of(date(2026, 9, 7)) == date(2026, 9, 7)   # сам понедельник
    assert monday_of(date(2026, 9, 13)) == date(2026, 9, 7)  # воскресенье


def test_anchor_week_is_odd():
    assert week_parity(ANCHOR, ANCHOR) == PARITY_ODD
    assert week_parity(ANCHOR + timedelta(days=4), ANCHOR) == PARITY_ODD


def test_next_week_is_even():
    assert week_parity(ANCHOR + timedelta(days=7), ANCHOR) == PARITY_EVEN


def test_parity_alternates_over_weeks():
    expected = [PARITY_ODD, PARITY_EVEN] * 5
    actual = [week_parity(ANCHOR + timedelta(weeks=i), ANCHOR) for i in range(10)]
    assert actual == expected


def test_parity_works_backwards_in_time():
    assert week_parity(ANCHOR - timedelta(days=7), ANCHOR) == PARITY_EVEN
    assert week_parity(ANCHOR - timedelta(days=14), ANCHOR) == PARITY_ODD


def test_no_anchor_means_no_parity():
    """Без опорной даты чётность неизвестна — расписание показываем целиком."""
    assert week_parity(date(2026, 9, 9), None) == PARITY_EVERY


# ── Проводится ли урок ────────────────────────────────────────────────────────

def test_weekly_lesson_always_happens():
    for offset in range(14):
        assert lesson_happens_on(PARITY_EVERY, ANCHOR + timedelta(days=offset), ANCHOR)


def test_odd_lesson_only_on_odd_week():
    assert lesson_happens_on(PARITY_ODD, ANCHOR, ANCHOR)
    assert not lesson_happens_on(PARITY_ODD, ANCHOR + timedelta(days=7), ANCHOR)


def test_even_lesson_only_on_even_week():
    assert not lesson_happens_on(PARITY_EVEN, ANCHOR, ANCHOR)
    assert lesson_happens_on(PARITY_EVEN, ANCHOR + timedelta(days=7), ANCHOR)


def test_without_anchor_all_lessons_shown():
    """
    Лучше показать лишний урок, чем скрыть настоящий: пока класс не указал
    текущую неделю, показываем оба варианта.
    """
    assert lesson_happens_on(PARITY_ODD, date(2026, 9, 9), None)
    assert lesson_happens_on(PARITY_EVEN, date(2026, 9, 9), None)


# ── Распознавание обозначений ─────────────────────────────────────────────────

def test_normalize_recognizes_russian_terms():
    for word in ("числитель", "Числитель", "нечётная", "верхняя", "первая"):
        assert normalize_parity(word) == PARITY_ODD
    for word in ("знаменатель", "Знаменатель", "чётная", "нижняя", "вторая"):
        assert normalize_parity(word) == PARITY_EVEN


def test_normalize_handles_abbreviations_with_dots():
    assert normalize_parity("чис.") == PARITY_ODD
    assert normalize_parity("знам.") == PARITY_EVEN


def test_normalize_unknown_means_every_week():
    assert normalize_parity("непонятно") == PARITY_EVERY
    assert normalize_parity("") == PARITY_EVERY
    assert normalize_parity(None) == PARITY_EVERY


def test_normalize_passes_canonical_values():
    assert normalize_parity("odd") == PARITY_ODD
    assert normalize_parity("even") == PARITY_EVEN


def test_suffix_only_for_alternating_lessons():
    assert parity_suffix(PARITY_EVERY) == ""
    assert "числитель" in parity_suffix(PARITY_ODD)
    assert "знаменатель" in parity_suffix(PARITY_EVEN)
