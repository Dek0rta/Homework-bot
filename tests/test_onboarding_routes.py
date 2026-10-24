"""
Регрессионные тесты доступности настройки по фото.

Онбординг изначально сделали только для групп, поэтому в личном чате
кнопка расписания вела в ручной редактор по клеткам, а присланное фото
трактовалось как домашнее задание. Эти тесты фиксируют, что путь по фото
доступен в обоих типах чатов.
"""

from __future__ import annotations

from aiogram import F
from aiogram.filters import Command

from src.bot import handlers_homework, handlers_private, onboarding
from src.core.constants import GROUP_TYPES


def _handler_names(router) -> set[str]:
    return {h.callback.__name__ for h in router.observers["message"].handlers}


def test_setup_command_exists_for_private_chat():
    """Регрессия: /setup существовал только для групп."""
    names = _handler_names(onboarding.router)
    assert "cmd_setup" in names          # группы
    assert "cmd_setup_private" in names  # личный чат


def test_photo_handler_checks_onboarding_first():
    """
    Фото в личке должно сначала проверяться как расписание.
    Иначе оно уходит в разбор домашнего задания и настройка невозможна.
    """
    import inspect

    source = inspect.getsource(handlers_homework.handle_photo)
    assert "try_parse_schedule_photo" in source

    # Проверка идёт до обработки как ДЗ
    assert source.index("try_parse_schedule_photo") < source.index("process_messages")


def test_album_handler_checks_onboarding_first():
    """Альбом из фото расписания во время настройки — тоже расписание."""
    import inspect

    source = inspect.getsource(handlers_homework.handle_album)
    assert source.index("try_parse_schedule_photo") < source.index("process_messages")


def test_text_handler_checks_onboarding_first():
    import inspect

    source = inspect.getsource(handlers_homework.handle_text)
    assert "try_parse_schedule_text" in source
    assert source.index("try_parse_schedule_text") < source.index("process_messages")


def test_schedule_button_offers_photo_path():
    """
    Кнопка «Изменить расписание» ведёт к фото, а не сразу в ручной редактор:
    ручной ввод — это до сотни нажатий.
    """
    import inspect

    source = inspect.getsource(handlers_private.btn_set_schedule)
    assert "start_awaiting" in source
    assert "фото" in source.lower()


def test_manual_editor_still_reachable():
    """Ручной ввод остаётся запасным путём, если фото не читается."""
    names = _handler_names(handlers_private.router)
    assert "cmd_schedule_manual" in names


def test_manual_editor_cancels_photo_waiting():
    """
    Переход в ручной редактор снимает ожидание фото, иначе следующее
    присланное изображение перехватит онбординг.
    """
    import inspect

    source = inspect.getsource(handlers_private.cmd_schedule_manual)
    assert "stop_awaiting" in source


def test_awaiting_state_is_per_chat():
    """Настройка в одном чате не должна влиять на другой."""
    onboarding.start_awaiting(-100)
    assert onboarding.is_awaiting_schedule(-100)
    assert not onboarding.is_awaiting_schedule(-200)
    onboarding.stop_awaiting(-100)
    assert not onboarding.is_awaiting_schedule(-100)
