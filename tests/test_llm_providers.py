"""
Провайдеры моделей: повторы, переход на запасной провайдер, ограничение
частоты и сборка запросов к GigaChat и Mistral.

Сеть не трогаем: клиенты SDK подменяются заглушками, которые записывают,
что им передали.
"""

import asyncio
from types import SimpleNamespace

import pytest

from src.services import llm_providers as lp


class HttpError(Exception):
    """Ошибка с кодом статуса — как их отдают SDK."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


class FakeProvider(lp.Provider):
    """Провайдер, который отвечает по сценарию: исключение или текст."""

    def __init__(self, name: str, script: list):
        super().__init__({"smart": "m"}, lp.Pacer(concurrency=5))
        self.name   = name
        self.script = list(script)
        self.calls  = 0

    async def _request(self, prompt, model, images, schema, max_tokens):
        self.calls += 1
        step = self.script.pop(0) if self.script else "ok"
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Паузы между повторами в тестах не нужны."""
    real_sleep = asyncio.sleep

    async def fast_sleep(delay, *args, **kwargs):
        await real_sleep(0)

    monkeypatch.setattr(lp.asyncio, "sleep", fast_sleep)


# ── Что повторять ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("exc", [
    asyncio.TimeoutError(),
    ConnectionError("connection reset"),
    OSError("network unreachable"),
    HttpError(429),
    HttpError(500),
    HttpError(503),
])
def test_transient_failures_are_retriable(exc):
    assert lp.is_retriable(exc)


@pytest.mark.parametrize("exc", [
    HttpError(400),
    HttpError(401),
    HttpError(404),
    HttpError(422),
    ValueError("invalid json"),
])
def test_client_errors_are_not_retriable(exc):
    """Повторять запрос с битым ключом или телом бессмысленно."""
    assert not lp.is_retriable(exc)


def test_retry_delay_honours_retry_after():
    exc = HttpError(429)
    exc.retry_after = 7.0
    assert lp._retry_delay(exc, attempt=0) == 7.0
    assert lp._retry_delay(HttpError(503), attempt=2) == 4.0


# ── Роутер ───────────────────────────────────────────────────────────────────

async def test_retries_then_succeeds():
    """503 на первой попытке, ответ на второй — вызывающий видит успех."""
    main   = FakeProvider("main", [HttpError(503), "ответ"])
    router = lp.LLMRouter([main])

    assert await router.complete("x") == "ответ"
    assert main.calls == 2


async def test_client_error_switches_provider_without_retries():
    """400 у основного не повторяем, а сразу идём к запасному."""
    main   = FakeProvider("main", [HttpError(400)])
    backup = FakeProvider("backup", ["запасной ответ"])
    router = lp.LLMRouter([main, backup])

    assert await router.complete("x") == "запасной ответ"
    assert main.calls == 1
    assert backup.calls == 1


async def test_exhausted_retries_fall_back():
    """Основной провайдер стабильно лежит — после попыток отвечает запасной."""
    main   = FakeProvider("main", [HttpError(503)] * 10)
    backup = FakeProvider("backup", ["ок"])
    router = lp.LLMRouter([main, backup])

    assert await router.complete("x") == "ок"
    assert main.calls == lp.ATTEMPTS_PER_PROVIDER


async def test_all_providers_down_raises_unavailable():
    router = lp.LLMRouter([
        FakeProvider("a", [HttpError(401)]),
        FakeProvider("b", [HttpError(401)]),
    ])
    with pytest.raises(lp.LLMUnavailable):
        await router.complete("x")


async def test_no_providers_raises_unavailable():
    with pytest.raises(lp.LLMUnavailable):
        await lp.LLMRouter([]).complete("x")


async def test_hanging_request_times_out(monkeypatch):
    """Зависший ответ прерывается, а не держит хендлер вечно."""
    monkeypatch.setattr(lp, "REQUEST_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(lp, "ATTEMPTS_PER_PROVIDER", 1)

    class Hanging(FakeProvider):
        async def _request(self, *args):
            await asyncio.Event().wait()

    with pytest.raises(lp.LLMUnavailable) as exc_info:
        await lp.LLMRouter([Hanging("slow", [])]).complete("x")
    assert isinstance(exc_info.value.__cause__, asyncio.TimeoutError)


async def test_images_are_capped():
    seen = {}

    class Recording(FakeProvider):
        async def _request(self, prompt, model, images, schema, max_tokens):
            seen["count"] = len(images)
            return "ok"

    images = [lp.ImageInput(b"x")] * (lp.MAX_IMAGES + 5)
    await lp.LLMRouter([Recording("r", [])]).complete("x", images=images)
    assert seen["count"] == lp.MAX_IMAGES


def test_model_for_tier_falls_back_to_smart():
    provider = FakeProvider("p", [])
    provider._models = {"smart": "big", "fast": "small"}
    assert provider.model_for("fast") == "small"
    assert provider.model_for("vision") == "big"


# ── Ограничитель частоты ─────────────────────────────────────────────────────

async def test_pacer_limits_concurrency():
    pacer   = lp.Pacer(concurrency=1)
    running = 0
    peak    = 0

    async def job():
        nonlocal running, peak
        async with pacer:
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0)
            running -= 1

    await asyncio.gather(*(job() for _ in range(5)))
    assert peak == 1


async def test_pacer_spaces_requests(monkeypatch):
    """Между стартами запросов выдерживается минимальный интервал."""
    waits = []
    real_sleep = asyncio.sleep

    async def record_sleep(delay, *args, **kwargs):
        waits.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(lp.asyncio, "sleep", record_sleep)
    pacer = lp.Pacer(concurrency=5, min_interval=10.0)

    async with pacer:
        pass
    async with pacer:
        pass

    assert waits and waits[0] > 9


# ── GigaChat ─────────────────────────────────────────────────────────────────

class FakeGigaClient:
    def __init__(self, fail_chat: bool = False):
        self.uploaded  = []
        self.deleted   = []
        self.chats     = []
        self.fail_chat = fail_chat

    async def aupload_file(self, file):
        self.uploaded.append(file)
        return SimpleNamespace(id_=f"file-{len(self.uploaded)}")

    async def adelete_file(self, file_id):
        self.deleted.append(file_id)

    async def achat(self, chat):
        self.chats.append(chat)
        if self.fail_chat:
            raise HttpError(500)
        msg = SimpleNamespace(content='  {"items": []}  ')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _giga(client) -> lp.GigaChatProvider:
    provider = lp.GigaChatProvider(
        credentials="key", scope="GIGACHAT_API_PERS", ca_bundle="ca.pem",
        models={"smart": "GigaChat-2-Max", "fast": "GigaChat-2", "vision": "GigaChat-2-Pro"},
    )
    provider._client = client
    return provider


async def test_gigachat_sends_each_photo_in_own_message():
    """Одно изображение на сообщение, инструкция — последней, файлы удаляются."""
    client   = FakeGigaClient()
    provider = _giga(client)
    images   = [lp.ImageInput(b"a", "image/jpeg"), lp.ImageInput(b"b", "image/png")]

    result = await provider.complete(
        "найди ДЗ", tier="smart", images=images, schema={"type": "object"}, max_tokens=100,
    )

    assert result == '{"items": []}'
    assert [f[0] for f in client.uploaded] == ["photo1.jpg", "photo2.png"]

    chat = client.chats[0]
    assert chat.model == "GigaChat-2-Max"
    assert [m.attachments for m in chat.messages] == [["file-1"], ["file-2"], None]
    assert chat.messages[-1].content == "найди ДЗ"
    assert chat.response_format.type == "json_schema"
    assert chat.response_format.schema_ == {"type": "object"}
    assert chat.response_format.strict is True
    assert client.deleted == ["file-1", "file-2"]


async def test_gigachat_deletes_files_even_when_chat_fails():
    client   = FakeGigaClient(fail_chat=True)
    provider = _giga(client)

    with pytest.raises(HttpError):
        await provider.complete(
            "x", tier="vision", images=[lp.ImageInput(b"a")], schema=None, max_tokens=10,
        )
    assert client.deleted == ["file-1"]
    assert client.chats[0].model == "GigaChat-2-Pro"


async def test_gigachat_text_only_has_no_attachments():
    client = FakeGigaClient()
    await _giga(client).complete("x", tier="fast", images=[], schema=None, max_tokens=10)

    chat = client.chats[0]
    assert chat.model == "GigaChat-2"
    assert len(chat.messages) == 1
    assert chat.response_format is None
    assert client.uploaded == []


# ── Mistral ──────────────────────────────────────────────────────────────────

class FakeMistralChat:
    def __init__(self):
        self.kwargs = None

    async def complete_async(self, **kwargs):
        self.kwargs = kwargs
        msg = SimpleNamespace(content="ok")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


async def test_mistral_builds_multimodal_request_with_schema():
    chat     = FakeMistralChat()
    provider = lp.MistralProvider(api_key="k", models={"smart": "ministral-14b-latest"})
    provider._pacer  = lp.Pacer(concurrency=1)
    provider._client = SimpleNamespace(chat=chat)

    await provider.complete(
        "prompt", tier="smart", images=[lp.ImageInput(b"\xff", "image/jpeg")],
        schema={"type": "object"}, max_tokens=50,
    )

    content = chat.kwargs["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "prompt"}
    assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,/w=="
    assert chat.kwargs["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert chat.kwargs["model"] == "ministral-14b-latest"


# ── Сборка из конфигурации ───────────────────────────────────────────────────

def test_build_providers_respects_order_and_keys(monkeypatch):
    from src.core import config

    monkeypatch.setattr(lp, "_mistral_installed", lambda: True)
    monkeypatch.setattr(config, "LLM_PROVIDERS", ["mistral", "gigachat"])
    monkeypatch.setattr(config, "MISTRAL_API_KEY", "m-key")
    monkeypatch.setattr(config, "GIGACHAT_CREDENTIALS", "g-key")
    assert [p.name for p in lp.build_providers()] == ["mistral", "gigachat"]

    monkeypatch.setattr(config, "MISTRAL_API_KEY", None)
    assert [p.name for p in lp.build_providers()] == ["gigachat"]


def test_set_router_overrides_singleton():
    router = lp.LLMRouter([])
    lp.set_router(router)
    try:
        assert lp.get_router() is router
    finally:
        lp.set_router(None)


def test_build_providers_skips_mistral_without_package(monkeypatch, caplog):
    """Нет пакета mistralai — бот работает на GigaChat, а не падает при старте."""
    from src.core import config

    monkeypatch.setattr(lp, "_mistral_installed", lambda: False)
    monkeypatch.setattr(config, "LLM_PROVIDERS", ["gigachat", "mistral"])
    monkeypatch.setattr(config, "MISTRAL_API_KEY", "m-key")
    monkeypatch.setattr(config, "GIGACHAT_CREDENTIALS", "g-key")

    with caplog.at_level("WARNING"):
        assert [p.name for p in lp.build_providers()] == ["gigachat"]
    assert "mistralai" in caplog.text
