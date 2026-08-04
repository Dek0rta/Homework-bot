"""Тесты формулы Stress Index и кеша LLM-оценок времени."""

from __future__ import annotations

import importlib

import pytest

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


# ── Кеш оценок времени ───────────────────────────────────────────────────────

@pytest.fixture
def analytics_mod(tmp_path, monkeypatch):
    """Модуль аналитики поверх изолированной БД."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from src.core import config as config_mod
    importlib.reload(config_mod)
    from src.core import db as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()

    from src.services import analytics as analytics_mod
    importlib.reload(analytics_mod)
    analytics_mod.migrate_analytics_schema()
    return analytics_mod


@pytest.mark.asyncio
async def test_identical_tasks_hit_llm_once(analytics_mod, monkeypatch):
    """Второй запрос того же задания должен обслуживаться кешем."""
    calls = []

    async def fake_ask(prompt: str) -> str:
        calls.append(prompt)
        return "45"

    monkeypatch.setattr(analytics_mod.llm, "ask_text", fake_ask)

    first  = await analytics_mod.estimate_hw_time("Физика", "§8 задачи 1-3")
    second = await analytics_mod.estimate_hw_time("Физика", "§8 задачи 1-3")

    assert first == second == 45
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cache_ignores_formatting_differences(analytics_mod, monkeypatch):
    """«§8, задачи 1-3» и «§ 8 задачи 1 3» — одно задание, один вызов."""
    calls = []

    async def fake_ask(prompt: str) -> str:
        calls.append(prompt)
        return "30"

    monkeypatch.setattr(analytics_mod.llm, "ask_text", fake_ask)

    await analytics_mod.estimate_hw_time("Физика", "§8, задачи 1-3")
    await analytics_mod.estimate_hw_time("физика", "§ 8   задачи 1 3")

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_different_tasks_each_hit_llm(analytics_mod, monkeypatch):
    calls = []

    async def fake_ask(prompt: str) -> str:
        calls.append(prompt)
        return "30"

    monkeypatch.setattr(analytics_mod.llm, "ask_text", fake_ask)

    await analytics_mod.estimate_hw_time("Физика", "§8")
    await analytics_mod.estimate_hw_time("Физика", "§9")

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_estimate_is_clamped_to_valid_range(analytics_mod, monkeypatch):
    async def absurd(prompt: str) -> str:
        return "9999"

    monkeypatch.setattr(analytics_mod.llm, "ask_text", absurd)
    assert await analytics_mod.estimate_hw_time("Физика", "бесконечная") == 240


@pytest.mark.asyncio
async def test_llm_failure_returns_none_and_is_not_cached(analytics_mod, monkeypatch):
    async def boom(prompt: str) -> str:
        raise RuntimeError("API down")

    monkeypatch.setattr(analytics_mod.llm, "ask_text", boom)
    assert await analytics_mod.estimate_hw_time("Физика", "§8") is None

    # Сбой не должен «залипнуть» в кеше — после починки API оценка проходит
    async def ok(prompt: str) -> str:
        return "40"

    monkeypatch.setattr(analytics_mod.llm, "ask_text", ok)
    assert await analytics_mod.estimate_hw_time("Физика", "§8") == 40
