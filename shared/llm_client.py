"""LLM-обёртка: единый интерфейс к Claude и GPT."""
from __future__ import annotations

import asyncio
import logging
import time

import anthropic
import openai

from shared.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_TIMEOUT,
    FALLBACK_RESPONSE,
    GPT_MODEL,
    GPT_TIMEOUT,
    OPENAI_API_KEY,
)

logger = logging.getLogger(__name__)

_claude_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
_gpt_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)


class LLMError(Exception):
    """Ошибка LLM-вызова (auth, превышение лимита, невосстановимая)."""


async def call_claude(
    messages: list[dict],
    system: str,
    max_tokens: int = 1024,
    timeout: int = CLAUDE_TIMEOUT,
) -> str:
    """Claude Sonnet для диалога. Prompt caching через cache_control."""
    system_block = [
        {'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}},
    ]
    attempt = 0
    max_attempts = 2
    while attempt < max_attempts:
        attempt += 1
        t0 = time.monotonic()
        try:
            coro = _claude_client.messages.create(
                model=CLAUDE_MODEL,
                system=system_block,
                messages=messages,
                max_tokens=max_tokens,
            )
            response = await asyncio.wait_for(coro, timeout=timeout)
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                'call_claude model=%s input_tokens=%d output_tokens=%d latency_ms=%d',
                CLAUDE_MODEL,
                response.usage.input_tokens,
                response.usage.output_tokens,
                latency_ms,
            )
            return response.content[0].text
        except anthropic.AuthenticationError as e:
            logger.error('call_claude error: %s', str(e))
            raise LLMError(str(e)) from e
        except (asyncio.TimeoutError, anthropic.APIError) as e:
            logger.error('call_claude error: %s', str(e))
            if attempt >= max_attempts:
                return FALLBACK_RESPONSE
            await asyncio.sleep(1)


async def call_gpt(
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 500,
    timeout: int = GPT_TIMEOUT,
    response_format: dict | None = None,
) -> str:
    """GPT-4o-mini для фоновых задач (JSON, анализ)."""
    full_messages = list(messages)
    if system is not None:
        full_messages = [{'role': 'system', 'content': system}, *full_messages]

    max_attempts = 3
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        t0 = time.monotonic()
        try:
            kwargs: dict = {
                'model': GPT_MODEL,
                'messages': full_messages,
                'max_tokens': max_tokens,
            }
            if response_format is not None:
                kwargs['response_format'] = response_format
            coro = _gpt_client.chat.completions.create(**kwargs)
            response = await asyncio.wait_for(coro, timeout=timeout)
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                'call_gpt model=%s input_tokens=%d output_tokens=%d latency_ms=%d',
                GPT_MODEL,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                latency_ms,
            )
            return response.choices[0].message.content
        except openai.AuthenticationError as e:
            logger.error('call_gpt error: %s', str(e))
            raise LLMError(str(e)) from e
        except (asyncio.TimeoutError, openai.APIError) as e:
            logger.error('call_gpt error: %s', str(e))
            last_error = e
            if attempt < max_attempts:
                delay = attempt
                await asyncio.sleep(delay)

    raise LLMError(str(last_error))
