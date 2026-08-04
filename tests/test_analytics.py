"""Тесты формулы Stress Index."""

from src.services.analytics import calculate_stress_index


def test_zero_tasks_gives_zero_index():
    assert calculate_stress_index(0, 60, 3) == 0.0


def test_zero_time_gives_zero_index():
    assert calculate_stress_index(5, 0, 3) == 0.0


def test_index_matches_formula():
    # 4 задачи × 30 мин = 2 часа, делим на 2 дня → 1.0
    assert calculate_stress_index(4, 30, 2) == 1.0


def test_closer_deadline_raises_index():
    far  = calculate_stress_index(4, 60, 4)
    near = calculate_stress_index(4, 60, 1)
    assert near > far


def test_more_tasks_raise_index():
    assert calculate_stress_index(8, 60, 2) > calculate_stress_index(2, 60, 2)


def test_zero_days_does_not_divide_by_zero():
    """days_until_deadline=0 не должен ронять — знаменатель зажат минимумом 1."""
    assert calculate_stress_index(2, 60, 0) == 2.0
