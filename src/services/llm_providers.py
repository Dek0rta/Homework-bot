"""
Провайдеры языковых моделей и выбор между ними.

Основной — GigaChat: бесплатный пакет для физлиц, работает с российских
серверов и читает фото. Запасной — Mistral: если Сбер недоступен или пакет
закончился, задания всё равно разбираются, просто моделью попроще.

Остальной код не знает, какой провайдер ответил. Он просит модель нужного
уровня (tier) и получает текст ответа.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import Literal, Sequence

import httpx

from src.core import config

logger = logging.getLogger(__name__)

Tier = Literal["smart", "fast", "vision"]
# smart  — личные ДЗ и расписание: важна точность, объём небольшой
# fast   — переписка чата класса: сообщений много, только текст
# vision — фото из чата класса: фото много, нужна модель с компьютерным зрением

# Ответ модели ждём не дольше этого: зависший запрос иначе держит хендлер
# бессрочно, и пользователь не получает ни ответа, ни ошибки.
REQUEST_TIMEOUT_SECONDS = 90

# Попыток на одного провайдера при временных сбоях, прежде чем перейти к следующему
ATTEMPTS_PER_PROVIDER = 3

# GigaChat принимает не больше 10 изображений в одном запросе
MAX_IMAGES = 10


@dataclass(frozen=True)
class ImageInput:
    """Изображение для модели: байты файла и его MIME-тип."""

    data: bytes
    mime: str = "image/jpeg"

    @property
    def extension(self) -> str:
        return {"image/png": "png", "image/bmp": "bmp", "image/tiff": "tiff"}.get(self.mime, "jpg")


class LLMUnavailable(RuntimeError):
    """Ни один провайдер не смог ответить."""


def is_retriable(exc: Exception) -> bool:
    """
    Стоит ли повторить запрос: таймауты, обрывы связи, 429 и 5xx.
    Повторять запрос с битым ключом или телом (4xx) бессмысленно.
    """
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError, httpx.TransportError)):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or 500 <= status < 600
    text = str(exc)
    return any(marker in text for marker in ("429", "500", "502", "503", "504", "timeout", "Timeout"))


def _retry_delay(exc: Exception, attempt: int) -> float:
    """Пауза перед повтором: сколько попросил сервер, иначе экспонента."""
    retry_after = getattr(exc, "retry_after", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        return min(float(retry_after), 30.0)
    return float(2 ** attempt)


class Pacer:
    """
    Ограничитель частоты: не больше `concurrency` запросов одновременно
    и не чаще одного раза в `min_interval` секунд.

    Бесплатные тарифы режут именно это: GigaChat обрабатывает один поток
    генерации, Mistral — 30 запросов в минуту. Без ограничителя всплеск
    сообщений в чате класса превращается в пачку ошибок 429.
    """

    def __init__(self, concurrency: int = 1, min_interval: float = 0.0):
        self._semaphore    = asyncio.Semaphore(concurrency)
        self._lock         = asyncio.Lock()
        self._min_interval = min_interval
        self._last_start   = 0.0

    async def __aenter__(self) -> None:
        await self._semaphore.acquire()
        if self._min_interval:
            async with self._lock:
                wait = self._last_start + self._min_interval - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_start = time.monotonic()

    async def __aexit__(self, *_exc) -> None:
        self._semaphore.release()


class Provider:
    """Общая часть провайдеров: выбор модели по уровню и ограничение частоты."""

    name = "base"

    def __init__(self, models: dict[str, str], pacer: Pacer):
        self._models = models
        self._pacer  = pacer

    def model_for(self, tier: Tier) -> str:
        return self._models.get(tier) or self._models["smart"]

    async def complete(
        self,
        prompt: str,
        *,
        tier: Tier,
        images: Sequence[ImageInput],
        schema: dict | None,
        max_tokens: int,
    ) -> str:
        async with self._pacer:
            return await asyncio.wait_for(
                self._request(prompt, self.model_for(tier), images, schema, max_tokens),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

    async def _request(
        self,
        prompt: str,
        model: str,
        images: Sequence[ImageInput],
        schema: dict | None,
        max_tokens: int,
    ) -> str:
        raise NotImplementedError


class GigaChatProvider(Provider):
    """
    GigaChat от Сбера. Фото сначала загружаются в файловое хранилище,
    в запрос уходят их идентификаторы; после ответа файлы удаляются.
    В одном сообщении допускается только одно изображение, поэтому каждое
    фото идёт отдельным сообщением, а инструкция — последним.
    """

    name = "gigachat"

    def __init__(self, credentials: str, scope: str, ca_bundle: str, models: dict[str, str]):
        # Freemium-режим обрабатывает генерацию в одном потоке
        super().__init__(models, Pacer(concurrency=1))
        self._credentials = credentials
        self._scope       = scope
        self._ca_bundle   = ca_bundle
        self._client      = None

    def _get_client(self):
        if self._client is None:
            from gigachat import GigaChat

            self._client = GigaChat(
                credentials=self._credentials,
                scope=self._scope,
                ca_bundle_file=self._ca_bundle,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        return self._client

    async def _request(self, prompt, model, images, schema, max_tokens) -> str:
        from gigachat.models import Chat, Messages, MessagesRole

        client   = self._get_client()
        file_ids: list[str] = []
        try:
            for i, image in enumerate(images, 1):
                uploaded = await client.aupload_file(
                    (f"photo{i}.{image.extension}", image.data, image.mime)
                )
                file_ids.append(uploaded.id_)

            messages = [
                Messages(
                    role=MessagesRole.USER,
                    content=f"Фото {i} из {len(file_ids)}.",
                    attachments=[file_id],
                )
                for i, file_id in enumerate(file_ids, 1)
            ]
            messages.append(Messages(role=MessagesRole.USER, content=prompt))

            chat = Chat(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
                response_format=(
                    {"type": "json_schema", "schema": schema, "strict": True} if schema else None
                ),
            )
            response = await client.achat(chat)
            return (response.choices[0].message.content or "").strip()
        finally:
            for file_id in file_ids:
                try:
                    await client.adelete_file(file_id)
                except Exception as e:
                    # Файл останется в хранилище — неприятно, но не повод
                    # терять уже полученный ответ
                    logger.warning("GigaChat: не удалось удалить файл %s: %s", file_id, e)


class MistralProvider(Provider):
    """Mistral. Фото передаются прямо в запросе как data URI."""

    name = "mistral"

    def __init__(self, api_key: str, models: dict[str, str]):
        # Бесплатный тариф: 30 запросов в минуту на модель
        super().__init__(models, Pacer(concurrency=2, min_interval=2.0))
        self._api_key = api_key
        self._client  = None

    def _get_client(self):
        if self._client is None:
            from mistralai import Mistral

            self._client = Mistral(api_key=self._api_key)
        return self._client

    async def _request(self, prompt, model, images, schema, max_tokens) -> str:
        if images:
            content: str | list[dict] = [{"type": "text", "text": prompt}] + [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.mime};base64,"
                               + base64.b64encode(image.data).decode("ascii"),
                    },
                }
                for image in images
            ]
        else:
            content = prompt

        kwargs: dict = {
            "model":       model,
            "messages":    [{"role": "user", "content": content}],
            "temperature": 0.1,
            "max_tokens":  max_tokens,
        }
        if schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema, "strict": True},
            }

        response = await self._get_client().chat.complete_async(**kwargs)
        return (response.choices[0].message.content or "").strip()


class LLMRouter:
    """
    Отправляет запрос основному провайдеру, при сбое — следующему.
    Временные сбои (таймаут, 429, 5xx) повторяются у того же провайдера.
    """

    def __init__(self, providers: Sequence[Provider]):
        self.providers = list(providers)

    async def complete(
        self,
        prompt: str,
        *,
        tier: Tier = "smart",
        images: Sequence[ImageInput] = (),
        schema: dict | None = None,
        max_tokens: int = 1500,
    ) -> str:
        if not self.providers:
            raise LLMUnavailable(
                "Не настроен ни один провайдер моделей — задай GIGACHAT_CREDENTIALS или MISTRAL_API_KEY"
            )

        images = list(images)[:MAX_IMAGES]
        last_error: Exception | None = None

        for provider in self.providers:
            try:
                return await self._with_retries(provider, prompt, tier, images, schema, max_tokens)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM: %s не ответил (%s: %s) — пробую следующий провайдер",
                    provider.name, type(exc).__name__, str(exc)[:200],
                )

        raise LLMUnavailable("Ни один провайдер не ответил") from last_error

    @staticmethod
    async def _with_retries(provider, prompt, tier, images, schema, max_tokens) -> str:
        for attempt in range(ATTEMPTS_PER_PROVIDER):
            try:
                return await provider.complete(
                    prompt, tier=tier, images=images, schema=schema, max_tokens=max_tokens,
                )
            except Exception as exc:
                if not is_retriable(exc) or attempt == ATTEMPTS_PER_PROVIDER - 1:
                    raise
                delay = _retry_delay(exc, attempt)
                logger.warning(
                    "LLM: %s — временный сбой (%s), повтор через %.0fs (попытка %d)",
                    provider.name, type(exc).__name__, delay, attempt + 1,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable: цикл повторов завершился без ответа и без исключения")


def build_providers() -> list[Provider]:
    """Провайдеры в порядке LLM_PROVIDERS; без ключа — пропускаются."""
    providers: list[Provider] = []
    for name in config.LLM_PROVIDERS:
        if name == "gigachat" and config.GIGACHAT_CREDENTIALS:
            providers.append(GigaChatProvider(
                credentials=config.GIGACHAT_CREDENTIALS,
                scope=config.GIGACHAT_SCOPE,
                ca_bundle=config.GIGACHAT_CA_BUNDLE,
                models={
                    "smart":  config.GIGACHAT_MODEL,
                    "fast":   config.GIGACHAT_FAST_MODEL,
                    "vision": config.GIGACHAT_VISION_MODEL,
                },
            ))
        elif name == "mistral" and config.MISTRAL_API_KEY:
            providers.append(MistralProvider(
                api_key=config.MISTRAL_API_KEY,
                models={
                    "smart":  config.MISTRAL_MODEL,
                    "fast":   config.MISTRAL_FAST_MODEL,
                    "vision": config.MISTRAL_MODEL,
                },
            ))
        elif name not in ("gigachat", "mistral"):
            logger.warning("LLM_PROVIDERS: неизвестный провайдер %r — пропускаю", name)
    return providers


_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter(build_providers())
        logger.info(
            "LLM: провайдеры — %s",
            ", ".join(p.name for p in _router.providers) or "не настроены",
        )
    return _router


def set_router(router: LLMRouter | None) -> None:
    """Подмена роутера — для тестов."""
    global _router
    _router = router
