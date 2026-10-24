"""Карточки ДЗ: текст, кнопки и ограничения Telegram на callback_data."""

from __future__ import annotations

from datetime import date

from src.bot import homework_cards as cards

TODAY  = date(2026, 10, 24)   # суббота
MONDAY = date(2026, 10, 26)
BIG_ID = 9_999_999


def _row(hw_id, subject="Алгебра", task="№245", due="2026-10-26", confidence=0.9, chat_id=1, done=0):
    return {
        "id": hw_id, "chat_id": chat_id, "subject": subject, "task": task,
        "due_date": due, "ai_confidence": confidence, "is_done": done,
    }


def _callbacks(keyboard) -> list[str]:
    return [b.callback_data for row in keyboard.inline_keyboard for b in row if b.callback_data]


def test_plural():
    assert [cards.plural(n, "задание", "задания", "заданий") for n in (1, 2, 5, 11, 21, 22)] == [
        "задание", "задания", "заданий", "заданий", "задание", "задания",
    ]


def test_date_label():
    assert cards.date_label(TODAY, TODAY) == "сегодня, сб, 24 окт"
    assert cards.date_label(date(2026, 10, 25), TODAY) == "завтра, вс, 25 окт"
    assert cards.date_label(MONDAY, TODAY) == "пн, 26 окт"
    assert cards.date_label(None, TODAY) == "без даты"


def test_card_lists_items_and_flags_low_confidence():
    rows = [_row(10), _row(11, "Физика", "§12", None, confidence=0.3)]
    text, keyboard = cards.render_card(rows, prefix="ph", first_id=10, last_id=11, today=TODAY)

    assert "Записал: 2 задания" in text
    assert "<b>Алгебра</b> — №245" in text
    assert "пн, 26 окт" in text
    assert "без даты" in text
    assert text.count("проверь") == 1

    callbacks = _callbacks(keyboard)
    assert "ph:due:10:10:11" in callbacks
    assert "ph:del:11:10:11" in callbacks
    assert "ph:undo:10:11" in callbacks
    assert "ph:list" in callbacks


def test_card_escapes_html():
    """Текст задания из сообщения не должен ломать разметку."""
    text, _ = cards.render_card([_row(1, task="решить <x> & y")], prefix="ph",
                                first_id=1, last_id=1, today=TODAY)
    assert "решить &lt;x&gt; &amp; y" in text


def test_group_card_has_no_personal_buttons():
    _, keyboard = cards.render_card([_row(1)], prefix="gh", first_id=1, last_id=1, today=TODAY)
    callbacks = _callbacks(keyboard)
    assert not any(c.startswith("ph:") for c in callbacks)
    assert "gh:due:1:1:1" in callbacks


def test_empty_card():
    text, keyboard = cards.render_card([], prefix="ph", first_id=1, last_id=2, today=TODAY)
    assert "удалены" in text
    assert keyboard is None


def test_due_options_mark_lessons_and_skip_sundays():
    options = cards.due_options([MONDAY, date(2026, 11, 9)], TODAY)
    dates = [d for d, _ in options]
    assert date(2026, 10, 25) not in dates            # воскресенье
    assert date(2026, 11, 9) in dates                 # урок за пределами недели
    assert dict(options)[MONDAY] is True
    assert dict(options)[date(2026, 10, 27)] is False
    assert dates == sorted(dates)


def test_callback_data_fits_telegram_limit():
    """Telegram отклоняет callback_data длиннее 64 байт — даже при больших id."""
    rows = [_row(BIG_ID - 1, subject="Обществознание и очень длинное название")]
    _, card_kb = cards.render_card(rows, prefix="gh", first_id=BIG_ID - 1, last_id=BIG_ID, today=TODAY)
    _, picker_kb = cards.render_due_picker(
        rows[0], prefix="gh", first_id=BIG_ID - 1, last_id=BIG_ID,
        lesson_dates=[MONDAY], today=TODAY,
    )
    _, list_kb = cards.render_list(
        [_row(BIG_ID, done=0)], own_chat_id=1, today=TODAY,
    )
    for keyboard in (card_kb, picker_kb, list_kb):
        for data in _callbacks(keyboard):
            assert len(data.encode()) <= 64, data


def test_picker_buttons_set_dates():
    _, keyboard = cards.render_due_picker(
        _row(5), prefix="ph", first_id=5, last_id=6, lesson_dates=[MONDAY], today=TODAY,
    )
    callbacks = _callbacks(keyboard)
    assert "ph:set:5:20261026:5:6" in callbacks
    assert "ph:set:5:0:5:6" in callbacks       # без даты
    assert "ph:card:5:6" in callbacks          # назад
    labels = [b.text for row in keyboard.inline_keyboard for b in row]
    assert "📚 пн 26.10" in labels


def test_list_groups_by_date_and_marks_shared():
    rows = [
        _row(1, due="2026-10-20", done=0),                  # просрочено
        _row(2, due="2026-10-20", done=1),                  # просрочено, но сделано — скрыть
        _row(3, due="2026-10-25", chat_id=-100),            # завтра, из класса
        _row(4, due=None),
    ]
    text, keyboard = cards.render_list(rows, own_chat_id=1, today=TODAY)

    assert "⏰ Просрочено" in text
    assert "Завтра, вс, 25 окт" in text
    assert "Без даты" in text
    assert text.count("👥") == 2          # пометка у задания класса и в подсказке
    callbacks = _callbacks(keyboard)
    assert "ph:done:2" not in callbacks
    assert callbacks == ["ph:done:1", "ph:done:3", "ph:done:4"]


def test_done_items_are_struck_through():
    text, keyboard = cards.render_list([_row(1, due="2026-10-26", done=1)], own_chat_id=1, today=TODAY)
    assert "<s>" in text
    assert keyboard.inline_keyboard[0][0].text == "↩️ 1"


def test_empty_list_offers_app():
    text, keyboard = cards.render_list([], own_chat_id=1, today=TODAY, web_app_url="https://app.example")
    assert "нет" in text
    assert keyboard.inline_keyboard[0][0].web_app.url == "https://app.example"


def test_list_is_capped():
    rows = [_row(i, due=None) for i in range(1, cards.LIST_LIMIT + 6)]
    text, keyboard = cards.render_list(rows, own_chat_id=1, today=TODAY)
    assert "ещё 5" in text
    assert len(_callbacks(keyboard)) == cards.LIST_LIMIT
