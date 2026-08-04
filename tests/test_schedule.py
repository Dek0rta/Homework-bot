"""Тесты вычисления дат ближайших уроков."""

from datetime import datetime, timedelta

from src.core.constants import lesson_number, time_key
from src.services.schedule import future_lesson_datetimes, next_lesson_datetime


def test_next_lesson_is_in_the_future():
    for day in range(7):
        dt = next_lesson_datetime(day, "10:10")
        assert dt > datetime.now() - timedelta(minutes=1)
        assert dt.weekday() == day


def test_next_lesson_keeps_requested_time():
    dt = next_lesson_datetime(2, "12:50")
    assert (dt.hour, dt.minute) == (12, 50)


def test_future_lessons_are_weekly_and_ordered():
    dts = future_lesson_datetimes(1, "8:15", n=3)
    assert len(dts) == 3
    assert dts == sorted(dts)
    assert dts[1] - dts[0] == timedelta(weeks=1)
    assert dts[2] - dts[1] == timedelta(weeks=1)
    assert all(d.weekday() == 1 for d in dts)


def test_lesson_number_maps_known_times():
    assert lesson_number("8:15") == 1
    assert lesson_number("12:00") == 5
    assert lesson_number("14:30") == 8


def test_lesson_number_handles_unknown_time():
    """Нестандартное время не должно ронять — попадает в ближайший слот."""
    assert 1 <= lesson_number("23:59") <= 8


def test_time_key_orders_times_correctly():
    times = ["12:00", "8:15", "10:10", "14:30"]
    assert sorted(times, key=time_key) == ["8:15", "10:10", "12:00", "14:30"]
