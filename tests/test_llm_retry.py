"""
Повторы и таймаут запросов к Mistral.

Раньше повторялась только ошибка 429, определённая подстрокой в тексте
исключения, а таймаута не было вовсе — зависший запрос держал хендлер
бессрочно.
"""

import asyncio
from unittest.mock import patch

import pytest

from src.services import llm


class HttpError(Exception):
    """Ошибка с кодом статуса — как их отдаёт SDK."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


@pytest.mark.parametrize("exc", [
    asyncio.TimeoutError(),
    ConnectionError("connection reset"),
    OSError("network unreachable"),
    HttpError(429),
    HttpError(500),
    HttpError(503),
])
def test_transient_failures_are_retriable(exc):
    assert llm._is_retriable(exc)


@pytest.mark.parametrize("exc", [
    HttpError(400),
    HttpError(401),
    HttpError(404),
    ValueError("invalid json"),
])
def test_client_errors_are_not_retriable(exc):
    """Повторять запрос с битым ключом или телом бессмысленно."""
    assert not llm._is_retriable(exc)


def _fake_response(text: str):
    class _Msg:
        content = text

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    return _Resp()


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    """503 на первой попытке, ответ на второй — вызывающий видит успех."""
    calls = []

    async def flaky(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise HttpError(503)
        return _fake_response("  ответ  ")

    with patch.object(llm._client.chat, "complete_async", side_effect=flaky), \
         patch.object(llm.asyncio, "sleep", return_value=None):
        result = await llm._chat([{"role": "user", "content": "x"}], "m")

    assert result == "ответ"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_client_error_fails_immediately():
    """400 не повторяем — иначе четыре бессмысленных запроса подряд."""
    calls = []

    async def bad_request(**kwargs):
        calls.append(1)
        raise HttpError(400)

    with patch.object(llm._client.chat, "complete_async", side_effect=bad_request):
        with pytest.raises(HttpError):
            await llm._chat([{"role": "user", "content": "x"}], "m")

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_exhausted_retries_raise():
    async def always_503(**kwargs):
        raise HttpError(503)

    with patch.object(llm._client.chat, "complete_async", side_effect=always_503), \
         patch.object(llm.asyncio, "sleep", return_value=None):
        with pytest.raises(HttpError):
            await llm._chat([{"role": "user", "content": "x"}], "m", max_retries=2)


@pytest.mark.asyncio
async def test_hanging_request_times_out(monkeypatch):
    """Зависший ответ модели прерывается, а не держит хендлер вечно."""
    monkeypatch.setattr(llm, "_REQUEST_TIMEOUT_SECONDS", 0.05)

    async def hang(**kwargs):
        await asyncio.sleep(30)

    # asyncio.sleep здесь не подменяем: на нём же держится wait_for
    with patch.object(llm._client.chat, "complete_async", side_effect=hang):
        with pytest.raises(asyncio.TimeoutError):
            await llm._chat([{"role": "user", "content": "x"}], "m", max_retries=1)
