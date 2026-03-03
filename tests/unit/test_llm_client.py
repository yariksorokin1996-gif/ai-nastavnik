"""
Тесты для shared/llm_client.py
13 тестов: call_claude (6) + call_gpt (7). Все LLM-вызовы замоканы.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import openai
import pytest

from shared.llm_client import FALLBACK_RESPONSE, LLMError, call_claude, call_gpt


# ---------------------------------------------------------------------------
# Хелперы для создания моков ответов
# ---------------------------------------------------------------------------


def make_claude_response(text="Привет!"):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage = MagicMock(input_tokens=100, output_tokens=50)
    return response


def make_gpt_response(text='{"key": "value"}'):
    response = MagicMock()
    choice = MagicMock()
    choice.message.content = text
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    return response


# ===========================================================================
# call_claude
# ===========================================================================


@pytest.mark.asyncio
@patch("shared.llm_client._claude_client")
async def test_call_claude_success(mock_client):
    """Успешный вызов Claude возвращает текст ответа."""
    mock_client.messages.create = AsyncMock(
        return_value=make_claude_response("Ответ Евы")
    )
    result = await call_claude(
        messages=[{"role": "user", "content": "Привет"}],
        system="Ты Ева",
    )
    assert result == "Ответ Евы"
    mock_client.messages.create.assert_awaited_once()


@pytest.mark.asyncio
@patch("shared.llm_client._claude_client")
async def test_call_claude_timeout(mock_client):
    """TimeoutError после всех попыток -> FALLBACK_RESPONSE."""
    mock_client.messages.create = AsyncMock(side_effect=asyncio.TimeoutError)
    result = await call_claude(
        messages=[{"role": "user", "content": "Привет"}],
        system="Ты Ева",
    )
    assert result == FALLBACK_RESPONSE


@pytest.mark.asyncio
@patch("shared.llm_client._claude_client")
async def test_call_claude_retry_success(mock_client):
    """Первый вызов APIError, второй OK -> возвращает текст."""
    mock_client.messages.create = AsyncMock(
        side_effect=[
            anthropic.APIError(
                message="server error",
                request=MagicMock(),
                body=None,
            ),
            make_claude_response("После retry"),
        ]
    )
    result = await call_claude(
        messages=[{"role": "user", "content": "Привет"}],
        system="Ты Ева",
    )
    assert result == "После retry"
    assert mock_client.messages.create.await_count == 2


@pytest.mark.asyncio
@patch("shared.llm_client._claude_client")
async def test_call_claude_all_retries_fail(mock_client):
    """Два APIError подряд -> FALLBACK_RESPONSE."""
    mock_client.messages.create = AsyncMock(
        side_effect=[
            anthropic.APIError(message="err1", request=MagicMock(), body=None),
            anthropic.APIError(message="err2", request=MagicMock(), body=None),
        ]
    )
    result = await call_claude(
        messages=[{"role": "user", "content": "Привет"}],
        system="Ты Ева",
    )
    assert result == FALLBACK_RESPONSE
    assert mock_client.messages.create.await_count == 2


@pytest.mark.asyncio
@patch("shared.llm_client._claude_client")
async def test_call_claude_auth_error(mock_client):
    """AuthenticationError -> LLMError (НЕ retry)."""
    mock_client.messages.create = AsyncMock(
        side_effect=anthropic.AuthenticationError(
            message="invalid api key",
            response=MagicMock(status_code=401),
            body=None,
        )
    )
    with pytest.raises(LLMError):
        await call_claude(
            messages=[{"role": "user", "content": "Привет"}],
            system="Ты Ева",
        )
    # Только 1 попытка, без retry
    assert mock_client.messages.create.await_count == 1


@pytest.mark.asyncio
@patch("shared.llm_client._claude_client")
async def test_call_claude_prompt_caching(mock_client):
    """system передаётся как list с cache_control."""
    mock_client.messages.create = AsyncMock(
        return_value=make_claude_response("OK")
    )
    await call_claude(
        messages=[{"role": "user", "content": "Привет"}],
        system="Системный промпт",
    )
    call_kwargs = mock_client.messages.create.call_args
    system_arg = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system")
    assert isinstance(system_arg, list)
    assert len(system_arg) == 1
    block = system_arg[0]
    assert block["type"] == "text"
    assert block["text"] == "Системный промпт"
    assert block["cache_control"] == {"type": "ephemeral"}


# ===========================================================================
# call_gpt
# ===========================================================================


@pytest.mark.asyncio
@patch("shared.llm_client._gpt_client")
async def test_call_gpt_success(mock_client):
    """Успешный вызов GPT возвращает текст."""
    mock_client.chat.completions.create = AsyncMock(
        return_value=make_gpt_response('{"result": "ok"}')
    )
    result = await call_gpt(
        messages=[{"role": "user", "content": "Проанализируй"}],
    )
    assert result == '{"result": "ok"}'
    mock_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
@patch("shared.llm_client._gpt_client")
async def test_call_gpt_json_format(mock_client):
    """response_format пробрасывается в kwargs."""
    mock_client.chat.completions.create = AsyncMock(
        return_value=make_gpt_response('{"a": 1}')
    )
    await call_gpt(
        messages=[{"role": "user", "content": "JSON"}],
        response_format={"type": "json_object"},
    )
    call_kwargs = mock_client.chat.completions.create.call_args
    assert call_kwargs.kwargs.get("response_format") == {"type": "json_object"}


@pytest.mark.asyncio
@patch("shared.llm_client._gpt_client")
async def test_call_gpt_system_prepended(mock_client):
    """Если system!=None, он добавляется первым в messages."""
    mock_client.chat.completions.create = AsyncMock(
        return_value=make_gpt_response("ok")
    )
    await call_gpt(
        messages=[{"role": "user", "content": "Вопрос"}],
        system="Ты аналитик",
    )
    call_kwargs = mock_client.chat.completions.create.call_args
    sent_messages = call_kwargs.kwargs.get("messages")
    assert sent_messages[0] == {"role": "system", "content": "Ты аналитик"}
    assert sent_messages[1] == {"role": "user", "content": "Вопрос"}


@pytest.mark.asyncio
@patch("shared.llm_client.asyncio.sleep", new_callable=AsyncMock)
@patch("shared.llm_client._gpt_client")
async def test_call_gpt_timeout(mock_client, mock_sleep):
    """TimeoutError после всех 3 попыток -> LLMError."""
    mock_client.chat.completions.create = AsyncMock(
        side_effect=asyncio.TimeoutError
    )
    with pytest.raises(LLMError):
        await call_gpt(
            messages=[{"role": "user", "content": "Привет"}],
        )
    assert mock_client.chat.completions.create.await_count == 3


@pytest.mark.asyncio
@patch("shared.llm_client.asyncio.sleep", new_callable=AsyncMock)
@patch("shared.llm_client._gpt_client")
async def test_call_gpt_retry_twice(mock_client, mock_sleep):
    """Первые 2 fail, третий OK -> возвращает текст."""
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            openai.APIError(
                message="err1", request=MagicMock(), body=None
            ),
            openai.APIError(
                message="err2", request=MagicMock(), body=None
            ),
            make_gpt_response("Третья попытка"),
        ]
    )
    result = await call_gpt(
        messages=[{"role": "user", "content": "Привет"}],
    )
    assert result == "Третья попытка"
    assert mock_client.chat.completions.create.await_count == 3
    # sleep вызывался 2 раза (перед 2-й и 3-й попыткой)
    assert mock_sleep.await_count == 2


@pytest.mark.asyncio
@patch("shared.llm_client.asyncio.sleep", new_callable=AsyncMock)
@patch("shared.llm_client._gpt_client")
async def test_call_gpt_all_retries_fail(mock_client, mock_sleep):
    """3 APIError подряд -> LLMError."""
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            openai.APIError(message="e1", request=MagicMock(), body=None),
            openai.APIError(message="e2", request=MagicMock(), body=None),
            openai.APIError(message="e3", request=MagicMock(), body=None),
        ]
    )
    with pytest.raises(LLMError):
        await call_gpt(
            messages=[{"role": "user", "content": "Привет"}],
        )
    assert mock_client.chat.completions.create.await_count == 3


@pytest.mark.asyncio
@patch("shared.llm_client._gpt_client")
async def test_call_gpt_auth_error(mock_client):
    """AuthenticationError -> LLMError (НЕ retry)."""
    mock_client.chat.completions.create = AsyncMock(
        side_effect=openai.AuthenticationError(
            message="bad key",
            response=MagicMock(status_code=401),
            body=None,
        )
    )
    with pytest.raises(LLMError):
        await call_gpt(
            messages=[{"role": "user", "content": "Привет"}],
        )
    # Только 1 попытка — auth error не ретраится
    assert mock_client.chat.completions.create.await_count == 1
