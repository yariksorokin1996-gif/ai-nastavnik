import re
import json
import asyncio
import anthropic
from bot.memory.database import (
    get_user, create_user, update_user, add_message,
    get_recent_messages, increment_sessions,
)
from bot.memory.context_builder import build_context
from bot.memory.pattern_detector import detect_and_store_patterns, deep_pattern_analysis
from shared.config import ANTHROPIC_API_KEY, CLAUDE_MODEL_MAIN, CLAUDE_MODEL_FAST, FREE_SESSIONS_LIMIT
from shared.safety import check_crisis

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


def strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^---+\s*$', '', text, flags=re.MULTILINE)
    return text.strip()

PHASE_TRANSITIONS = {
    "onboarding": "diagnosis",
    "diagnosis": "goal",
    "goal": "planning",
    "planning": "daily",
    "daily": "daily",
}

PHASE_KEYWORDS = {
    "diagnosis": ["цель", "хочу", "стремлюсь", "мечтаю", "проблема", "область", "сфера"],
    "goal": ["конкретн", "измерим", "срок", "дедлайн", "результат"],
    "planning": ["план", "шаги", "действия", "с чего начать"],
    "daily": ["сделал", "не сделал", "выполнил", "провалил"],
}

RESET_KEYWORDS = ["хочу новую цель", "начать сначала", "сменить тему", "другая цель", "новая тема"]


def _should_advance_phase(current_phase: str, sessions: int) -> bool:
    thresholds = {
        "onboarding": 1,
        "diagnosis": 4,
        "goal": 6,
        "planning": 8,
    }
    return sessions >= thresholds.get(current_phase, 999)


async def _check_content_readiness(telegram_id: int, target_phase: str) -> bool:
    """Check if user messages contain keywords indicating readiness for target_phase."""
    keywords = PHASE_KEYWORDS.get(target_phase, [])
    if not keywords:
        return False
    messages = await get_recent_messages(telegram_id, limit=10)
    for msg in messages:
        if msg["role"] != "user":
            continue
        text_lower = msg["content"].lower()
        for kw in keywords:
            if kw in text_lower:
                return True
    return False


async def _extract_commitment(assistant_text: str):
    """Extract a commitment/action from the assistant's response using Claude Haiku."""
    try:
        haiku_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        response = await haiku_client.messages.create(
            model=CLAUDE_MODEL_FAST,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    "Проанализируй ответ наставника. Если в нём есть конкретное "
                    "обязательство/задание для пользователя с дедлайном, верни JSON: "
                    "{\"action\": \"описание действия\", \"deadline\": \"когда\"}. "
                    "Если нет конкретного обязательства — верни JSON: {\"action\": null}. "
                    "Отвечай ТОЛЬКО JSON, без пояснений.\n\n"
                    f"Ответ наставника:\n{assistant_text}"
                ),
            }],
        )
        raw = response.content[0].text.strip()
        result = json.loads(raw)
        if result.get("action") is not None:
            return result
        return None
    except Exception:
        return None


async def process_message(telegram_id: int, user_name: str, user_text: str) -> str:
    # Пустые/пробельные сообщения
    if not user_text or not user_text.strip():
        return "Напиши что-нибудь — я здесь."

    # Получаем или создаём пользователя
    user = await get_user(telegram_id)
    if not user:
        user = await create_user(telegram_id, user_name)

    # Проверка кризисных слов
    crisis_type, crisis_response = check_crisis(user_text)
    if crisis_type and crisis_type != "soft_signal":
        return crisis_response
    if crisis_type == "soft_signal":
        user["_soft_crisis"] = True

    # Детектируем паттерны в сообщении пользователя
    await detect_and_store_patterns(telegram_id, user_text)

    # Сохраняем сообщение пользователя
    await add_message(telegram_id, "user", user_text)

    # Строим контекст (системный промпт + история)
    system_prompt, messages = await build_context(user)

    # Запрос к Claude с ретраем при пустом ответе или rate limit
    assistant_text = None
    for attempt in range(5):
        try:
            response = await client.messages.create(
                model=CLAUDE_MODEL_MAIN,
                max_tokens=700,
                system=system_prompt,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            )
            if response.content and response.content[0].text.strip():
                assistant_text = strip_markdown(response.content[0].text)
                break
        except anthropic.RateLimitError:
            wait = 2 ** attempt  # 1, 2, 4, 8, 16 секунд
            await asyncio.sleep(wait)
            continue
        except anthropic.APIError:
            if attempt < 4:
                await asyncio.sleep(2)
            continue
        if attempt < 4:
            await asyncio.sleep(1)
    if not assistant_text:
        return "Произошла ошибка, попробуй ещё раз."

    # Сохраняем ответ наставника
    await add_message(telegram_id, "assistant", assistant_text)

    # В режиме поддержки: пропускаем обязательства, инкремент сессий, глубокий анализ и фазы
    if user.get("mode") == "support":
        return assistant_text

    # Извлекаем обязательства в фоне (не блокируем ответ)
    async def _background_commitment(tid: int, text: str):
        commitment = await _extract_commitment(text)
        if commitment:
            user_fresh = await get_user(tid)
            commitments = user_fresh.get("commitments", [])
            commitments.append(commitment)
            commitments = commitments[-5:]
            await update_user(tid, commitments=commitments)

    asyncio.create_task(_background_commitment(telegram_id, assistant_text))

    # Инкрементируем счётчик сессий
    await increment_sessions(telegram_id)

    # LLM-based pattern analysis every 5 messages
    await deep_pattern_analysis(telegram_id, user["sessions_count"] + 1)

    # Проверяем сброс фазы по ключевым словам
    current_phase = user["phase"]
    user_text_lower = user_text.lower()
    if current_phase != "onboarding":
        if any(kw in user_text_lower for kw in RESET_KEYWORDS):
            await update_user(telegram_id, phase="diagnosis", sessions_count=2)
            return assistant_text

    # Проверяем переход фазы
    new_sessions = user["sessions_count"] + 1
    if _should_advance_phase(current_phase, new_sessions):
        next_phase = PHASE_TRANSITIONS.get(current_phase, current_phase)
        if next_phase != current_phase:
            # onboarding -> diagnosis: advance unconditionally (onboarding is just "hello")
            if current_phase == "onboarding":
                await update_user(telegram_id, phase=next_phase)
            else:
                # All other transitions require content readiness
                if await _check_content_readiness(telegram_id, next_phase):
                    await update_user(telegram_id, phase=next_phase)

    return assistant_text
