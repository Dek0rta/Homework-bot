"""
Тесты предфильтра сообщений группы.

Ключевой критерий — асимметрия: пропустить лишнее в LLM дёшево,
потерять настоящее ДЗ дорого. Поэтому тесты на реальные формулировки
заданий строже, чем на отсев болтовни.
"""

from __future__ import annotations

import pytest

from src.services.prefilter import (
    has_homework_markers,
    normalize_task,
    should_analyze,
)

# Формулировки, которые обязаны дойти до модели
REAL_HOMEWORK = [
    "ДЗ по физике: §8 задачи 1-3",
    "На пятницу выучить стихотворение",
    "Математика — стр.45 упр.7, сдать в четверг",
    "Не забудьте параграф 12 прочитать к завтрашнему уроку химии",
    "englishу HW p. 30 ex. 4",
    "Задали написать сочинение про осень",
    "нужно сделать презентацию к понедельнику",
    "Ребята, на завтра номер 245 и 246",
    "по геометрии задача 15, кто не сделал",
    "Unit 5 vocabulary выучить наизусть",
    "принести конспект по истории",
    "решить примеры из таблицы на странице 12",
]

# Явная переписка — можно не тратить вызов модели
CHITCHAT = [
    "Привет всем!",
    "Спасибо за помощь",
    "Спасибо большое, очень выручил",
    "Доброе утро, ребята",
    "ага",
    "+",
    "ок",
    "Понял, спасибо",
    "хахаха",
    "Пока, до завтра",
]


@pytest.mark.parametrize("text", REAL_HOMEWORK)
def test_real_homework_reaches_llm(text):
    assert should_analyze(text), f"ДЗ отфильтровано по ошибке: {text!r}"


@pytest.mark.parametrize("text", CHITCHAT)
def test_chitchat_is_filtered_out(text):
    assert not should_analyze(text), f"Болтовня прошла фильтр: {text!r}"


def test_empty_and_none_are_filtered():
    assert not should_analyze(None)
    assert not should_analyze("")
    assert not should_analyze("   ")


def test_too_short_is_filtered():
    assert not should_analyze("дз")
    assert not should_analyze("хм")


def test_long_unfamiliar_phrasing_still_reaches_llm():
    """
    Без явных маркеров, но длинное и осмысленное — отдаём модели.
    Терять настоящее ДЗ хуже, чем сделать лишний вызов.
    """
    text = "Ребята, к следующему разу посмотрите первые две главы, будем обсуждать"
    assert should_analyze(text)


def test_marker_beats_chitchat_opener():
    """Сообщение с приветствием, но и с ДЗ, должно дойти до модели."""
    assert should_analyze("Привет всем! ДЗ по алгебре номер 12")


def test_has_homework_markers_detects_references():
    assert has_homework_markers("§8")
    assert has_homework_markers("стр. 45")
    assert has_homework_markers("p. 30")
    assert has_homework_markers("№15")
    assert not has_homework_markers("просто текст без ничего")


# ── Нормализация для кеша оценок ──────────────────────────────────────────────

def test_normalize_ignores_punctuation_and_case():
    a = normalize_task("Физика", "§8, задачи 1-3")
    b = normalize_task("физика", "§ 8   задачи 1 3")
    assert a == b


def test_normalize_distinguishes_different_tasks():
    assert normalize_task("Физика", "§8 задачи 1-3") != normalize_task("Физика", "§9 задачи 1-3")


def test_normalize_distinguishes_subjects():
    assert normalize_task("Физика", "§8") != normalize_task("Химия", "§8")
