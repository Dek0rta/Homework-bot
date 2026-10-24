"""
Сквозной сценарий личного чата через настоящий диспетчер aiogram.

Telegram подменён записывающей сессией, модель — заглушкой. Проверяется
то, что юнит-тесты не видят: апдейт доходит до нужного хендлера через
все роутеры в том же порядке, что в main.py, и кнопки карточки работают.
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

USER = 777


class RecordingSession(BaseSession):
    """Сессия-заглушка: записывает вызовы Bot API и отвечает правдоподобно."""

    def __init__(self):
        super().__init__()
        self.requests: list[TelegramMethod] = []
        self._message_id = 1000

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            self._message_id += 1
            # Как настоящий клиент: ответ привязан к боту, чтобы на нём
            # можно было вызывать .edit_text() и прочие методы
            return Message(
                message_id=getattr(method, "message_id", None) or self._message_id,
                date=datetime.now(),
                chat=Chat(id=method.chat_id or USER, type="private"),
                text=method.text,
            ).as_(bot)
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def close(self):
        pass

    def sent(self, kind) -> list:
        return [r for r in self.requests if isinstance(r, kind)]


class ScriptedProvider:
    """Модель-заглушка: на разбор ДЗ отвечает заданным JSON."""

    name = "fake"

    def __init__(self, items: list[dict]):
        self.items   = items
        self.prompts = []

    async def complete(self, prompt, *, tier, images, schema, max_tokens):
        self.prompts.append(prompt)
        if schema is None:
            return "30"  # оценка времени
        return json.dumps({"items": self.items}, ensure_ascii=False)


@pytest.fixture(scope="module")
def dispatcher():
    """Роутеры в том же порядке, что в main.py. Роутер подключается один раз за процесс."""
    from src.bot import (
        handlers_edit, handlers_group, handlers_homework, handlers_metrics,
        handlers_private, handlers_reminders, onboarding,
    )
    dp = Dispatcher(storage=MemoryStorage())
    for module in (onboarding, handlers_reminders, handlers_metrics, handlers_edit,
                   handlers_private, handlers_homework, handlers_group):
        dp.include_router(module.router)
    return dp


@pytest.fixture
def env(tmp_path, monkeypatch, dispatcher):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from src.core import config as config_mod
    importlib.reload(config_mod)
    from src.core import db as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()

    from src.services import llm_providers
    session = RecordingSession()
    bot     = Bot(token="42:TEST", session=session)
    yield dispatcher, bot, session, db_mod, llm_providers
    llm_providers.set_router(None)


def _text_update(text: str, update_id: int = 1) -> Update:
    return Update(update_id=update_id, message=Message(
        message_id=update_id,
        date=datetime.now(),
        chat=Chat(id=USER, type="private"),
        from_user=User(id=USER, is_bot=False, first_name="Тест"),
        text=text,
    ))


def _callback_update(data: str, message_id: int) -> Update:
    return Update(update_id=99, callback_query=CallbackQuery(
        id="cb", chat_instance="ci", data=data,
        from_user=User(id=USER, is_bot=False, first_name="Тест"),
        message=Message(message_id=message_id, date=datetime.now(),
                        chat=Chat(id=USER, type="private"), text="карточка"),
    ))


def _use_model(llm_providers, items) -> ScriptedProvider:
    provider = ScriptedProvider(items)
    llm_providers.set_router(llm_providers.LLMRouter([provider]))
    return provider


async def test_text_homework_is_saved_and_shown(env):
    dp, bot, session, db, llm_providers = env
    from src.core import clock
    due = (clock.today() + timedelta(days=3)).isoformat()
    _use_model(llm_providers, [
        {"subject": "Алгебра", "task": "№245, 247", "due_date": due, "confidence": 0.95},
        {"subject": "Физика", "task": "§12", "due_date": None, "confidence": 0.4},
    ])

    await dp.feed_update(bot, _text_update("алгебра 245 247, физика 12"))

    rows = db.get_upcoming_homework([USER], USER, clock.today().isoformat())
    assert [(r["subject"], r["due_date"]) for r in rows] == [("Алгебра", due), ("Физика", None)]

    card = session.sent(EditMessageText)[-1]
    assert "Записал: 2 задания" in card.text
    assert "проверь" in card.text              # низкая уверенность у физики
    assert "/setup" in card.text               # расписания нет — подсказка
    callbacks = [b.callback_data for row in card.reply_markup.inline_keyboard for b in row]
    assert any(c.startswith("ph:remind:") for c in callbacks)


async def test_card_button_changes_due_date(env):
    dp, bot, session, db, llm_providers = env
    _use_model(llm_providers, [{"subject": "Химия", "task": "№1", "due_date": None, "confidence": 1}])

    await dp.feed_update(bot, _text_update("химия номер 1"))
    hw_id = db.get_upcoming_homework([USER], USER, "2000-01-01")[0]["id"]

    await dp.feed_update(bot, _callback_update(f"ph:set:{hw_id}:20991231:{hw_id}:{hw_id}", 5000))

    assert db.get_homework(hw_id)["due_date"] == "2099-12-31"
    assert session.sent(AnswerCallbackQuery)


async def test_card_cannot_touch_someone_elses_homework(env):
    """Подделанный callback с чужим id не меняет чужое задание."""
    dp, bot, session, db, _ = env
    foreign = db.save_chat_homework(888, "Физика", "чужое", None, created_by=888)

    await dp.feed_update(bot, _callback_update(f"ph:del:{foreign}:{foreign}:{foreign}", 5000))

    assert db.get_homework(foreign) is not None
    answer = session.sent(AnswerCallbackQuery)[-1]
    assert answer.show_alert


async def test_chitchat_gets_helpful_reply(env):
    dp, bot, session, db, llm_providers = env
    _use_model(llm_providers, [])

    await dp.feed_update(bot, _text_update("привет, как дела?"))

    assert "Не нашёл" in session.sent(EditMessageText)[-1].text
    assert db.get_upcoming_homework([USER], USER, "2000-01-01") == []


async def test_model_outage_is_reported(env):
    dp, bot, session, db, llm_providers = env
    llm_providers.set_router(llm_providers.LLMRouter([]))

    await dp.feed_update(bot, _text_update("алгебра 245"))

    assert "не отвечает" in session.sent(EditMessageText)[-1].text


async def test_menu_button_is_not_parsed_as_homework(env):
    dp, bot, session, db, llm_providers = env
    provider = _use_model(llm_providers, [])

    await dp.feed_update(bot, _text_update("📋 Мои ДЗ"))

    assert provider.prompts == []
    assert "Домашних заданий нет" in session.sent(SendMessage)[-1].text


async def test_undo_removes_whole_batch(env):
    dp, bot, session, db, llm_providers = env
    _use_model(llm_providers, [
        {"subject": "А", "task": "1", "due_date": None, "confidence": 1},
        {"subject": "Б", "task": "2", "due_date": None, "confidence": 1},
    ])
    await dp.feed_update(bot, _text_update("два задания"))
    ids = [r["id"] for r in db.get_upcoming_homework([USER], USER, "2000-01-01")]

    await dp.feed_update(bot, _callback_update(f"ph:undo:{min(ids)}:{max(ids)}", 5000))

    assert db.get_upcoming_homework([USER], USER, "2000-01-01") == []
    assert "Отменил" in session.sent(EditMessageText)[-1].text


# ── Чат класса ───────────────────────────────────────────────────────────────

CLASS = -100500


def _group_update(text: str, update_id: int = 50) -> Update:
    return Update(update_id=update_id, message=Message(
        message_id=update_id,
        date=datetime.now(),
        chat=Chat(id=CLASS, type="supergroup"),
        from_user=User(id=USER, is_bot=False, first_name="Тест"),
        text=text,
    ))


async def test_group_homework_saved_with_date_from_schedule(env):
    """В чате класса задание записывается сразу — без вопроса «на какой день»."""
    dp, bot, session, db, llm_providers = env
    from src.core import clock
    from src.services import homework_intake as intake

    db.save_class_schedule(CLASS, [{"day": d, "slot": 1, "subject": "Физика"} for d in range(6)])
    db.set_chat_subjects(CLASS, ["Физика"])
    _use_model(llm_providers, [{"subject": "физика", "task": "§8 задачи 1-3", "due_date": None, "confidence": 0.9}])

    await dp.feed_update(bot, _group_update("ДЗ по физике §8 задачи 1-3"))

    [row] = db.get_chat_homework(CLASS)
    expected = intake.ClassSchedule(CLASS).next_lesson("Физика", clock.today())
    assert row["subject"] == "Физика"
    assert row["due_date"] == expected.isoformat()

    card = session.sent(SendMessage)[-1]
    assert "Записал в список класса" in card.text
    callbacks = [b.callback_data for r in card.reply_markup.inline_keyboard for b in r]
    assert callbacks[0].startswith("gh:due:")


async def test_group_chitchat_never_reaches_model(env):
    dp, bot, session, db, llm_providers = env
    db.set_chat_subjects(CLASS, ["Физика"])
    provider = _use_model(llm_providers, [])

    await dp.feed_update(bot, _group_update("привет всем!"))

    assert provider.prompts == []


async def test_group_delete_requires_admin(env):
    dp, bot, session, db, _ = env
    hw = db.save_chat_homework(CLASS, "Физика", "§8", None)

    update = Update(update_id=98, callback_query=CallbackQuery(
        id="cb", chat_instance="ci", data=f"gh:del:{hw}:{hw}:{hw}",
        from_user=User(id=USER, is_bot=False, first_name="Тест"),
        message=Message(message_id=1, date=datetime.now(),
                        chat=Chat(id=CLASS, type="supergroup"), text="карточка"),
    ))
    await dp.feed_update(bot, update)

    assert db.get_homework(hw) is not None
    assert "администратор" in session.sent(AnswerCallbackQuery)[-1].text
