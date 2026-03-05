"""Тесты модуля кризисного детектирования shared.safety."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest



# ---------------------------------------------------------------------------
# Level 3 -- суицид (мгновенно, без LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("shared.safety.call_gpt")
async def test_level3_suicide_keyword(mock_gpt: AsyncMock) -> None:
    """Level 3: 'хочу умереть' -> level=3, trigger найден, LLM НЕ вызывается."""
    from shared.safety import detect_crisis

    result = await detect_crisis("хочу умереть")

    assert result.level == 3
    assert result.trigger == "хочу умереть"
    assert result.is_verified is True
    mock_gpt.assert_not_called()


@pytest.mark.asyncio
@patch("shared.safety.call_gpt")
async def test_level3_no_llm_call(mock_gpt: AsyncMock) -> None:
    """Level 3: для любого суицидального ключевого слова LLM никогда не вызывается."""
    from shared.safety import detect_crisis

    result = await detect_crisis("Я думаю о суициде постоянно")

    assert result.level == 3
    assert result.trigger == "суицид"
    assert result.is_verified is True
    mock_gpt.assert_not_called()


# ---------------------------------------------------------------------------
# Level 2 -- насилие / самоповреждение (с LLM-верификацией)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("shared.safety.call_gpt")
async def test_level2_violence_confirmed(mock_gpt: AsyncMock) -> None:
    """Level 2: 'муж бьёт меня' + LLM подтверждает -> level=2."""
    mock_gpt.return_value = json.dumps({
        "is_real_crisis": True,
        "reason": "Прямое описание насилия",
    })
    from shared.safety import detect_crisis

    result = await detect_crisis("муж бьёт меня каждый вечер")

    assert result.level == 2
    assert result.trigger == "бьёт меня"
    assert result.is_verified is True
    mock_gpt.assert_called_once()


@pytest.mark.asyncio
@patch("shared.safety.call_gpt")
async def test_level2_false_positive(mock_gpt: AsyncMock) -> None:
    """Level 2: фигура речи -> LLM возвращает false -> level=0."""
    mock_gpt.return_value = json.dumps({
        "is_real_crisis": False,
        "reason": "фигура речи",
    })
    from shared.safety import detect_crisis

    # "передоз" -- ключевое слово level 2, но контекст нормальный
    result = await detect_crisis("умираю от смеха, передоз юмора на работе")

    assert result.level == 0
    assert result.trigger is None
    assert result.is_verified is True
    mock_gpt.assert_called_once()


# ---------------------------------------------------------------------------
# Level 1 -- мягкие сигналы (с LLM-верификацией)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("shared.safety.call_gpt")
async def test_level1_soft_signal(mock_gpt: AsyncMock) -> None:
    """Level 1: 'зачем всё это' + LLM подтверждает -> level=1."""
    mock_gpt.return_value = json.dumps({
        "is_real_crisis": True,
        "reason": "Экзистенциальный кризис",
    })
    from shared.safety import detect_crisis

    result = await detect_crisis("зачем всё это, я не вижу смысла")

    assert result.level == 1
    assert result.trigger == "зачем всё это"
    assert result.is_verified is True
    mock_gpt.assert_called_once()


# ---------------------------------------------------------------------------
# Level 0 -- чистый текст
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("shared.safety.call_gpt")
async def test_level0_clean_text(mock_gpt: AsyncMock) -> None:
    """Level 0: нет ключевых слов -> level=0, LLM НЕ вызывается."""
    from shared.safety import detect_crisis

    result = await detect_crisis("сегодня хороший день")

    assert result.level == 0
    assert result.trigger is None
    assert result.is_verified is True
    mock_gpt.assert_not_called()


# ---------------------------------------------------------------------------
# Ошибки LLM -- conservative (считаем кризисом)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("shared.safety.call_gpt")
async def test_llm_timeout_conservative(mock_gpt: AsyncMock) -> None:
    """LLM выбрасывает LLMError -> conservative: оставляем уровень кризиса."""
    from shared.llm_client import LLMError
    from shared.safety import detect_crisis

    mock_gpt.side_effect = LLMError("timeout")

    result = await detect_crisis("муж бьёт меня")

    assert result.level == 2
    assert result.trigger == "бьёт меня"
    assert result.is_verified is True


@pytest.mark.asyncio
@patch("shared.safety.call_gpt")
async def test_llm_invalid_json(mock_gpt: AsyncMock) -> None:
    """LLM возвращает не-JSON -> conservative: оставляем уровень кризиса."""
    mock_gpt.return_value = "this is not json at all"
    from shared.safety import detect_crisis

    result = await detect_crisis("нет больше сил жить дальше")

    assert result.level == 1
    assert result.trigger == "нет больше сил"
    assert result.is_verified is True
