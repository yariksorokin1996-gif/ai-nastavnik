import json
import anthropic
from shared.config import ANTHROPIC_API_KEY, CLAUDE_MODEL_FAST
from bot.memory.database import add_pattern, get_recent_messages

_haiku_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

EXCUSE_PATTERNS = {
    "weak_commitment": {
        "triggers": ["попробую", "постараюсь", "наверное сделаю", "может сделаю"],
        "label": "Слабое обязательство ('попробую' вместо 'сделаю')",
    },
    "no_time": {
        "triggers": ["нет времени", "нет время", "когда будет время", "не успеваю", "некогда"],
        "label": "Отмазка 'нет времени'",
    },
    "vague": {
        "triggers": ["наверное", "возможно", "может быть", "когда-нибудь", "скоро"],
        "label": "Размытые формулировки без конкретики",
    },
    "blame_external": {
        "triggers": ["из-за него", "из-за неё", "из-за них", "обстоятельства", "не дают", "мешают"],
        "label": "Перекладывание ответственности на внешние факторы",
    },
    "not_ready": {
        "triggers": ["ещё не готов", "не готова", "нужно подготовиться", "не время"],
        "label": "Паттерн 'ещё не готов'",
    },
    "low_self_worth": {
        "triggers": ["я не достойна", "я не заслуживаю", "кто я такая", "я никто", "я ничего не стою"],
        "label": "Самообесценивание ('я не достойна')",
    },
    "too_late": {
        "triggers": ["мне поздно", "уже не в том возрасте", "время упущено", "поезд ушёл", "слишком поздно"],
        "label": "Убеждение 'мне поздно что-то менять'",
    },
    "must_endure": {
        "triggers": ["нужно терпеть", "все так живут", "бывает и хуже", "надо смириться", "такова жизнь"],
        "label": "Паттерн 'нужно терпеть'",
    },
    "guilt_pattern": {
        "triggers": ["я виновата", "это из-за меня", "я плохая мать", "я плохая жена", "всё из-за меня"],
        "label": "Чувство вины ('я виновата во всём')",
    },
}


async def detect_and_store_patterns(telegram_id: int, user_message: str):
    """Анализирует сообщение пользователя и сохраняет выявленные паттерны."""
    text_lower = user_message.lower()
    for pattern_key, pattern_data in EXCUSE_PATTERNS.items():
        for trigger in pattern_data["triggers"]:
            if trigger in text_lower:
                await add_pattern(
                    telegram_id=telegram_id,
                    pattern_type=pattern_key,
                    pattern_text=pattern_data["label"],
                )
                break


async def deep_pattern_analysis(telegram_id: int, sessions_count: int):
    """Run LLM-based pattern analysis every 5 messages."""
    if sessions_count % 5 != 0 or sessions_count == 0:
        return

    messages = await get_recent_messages(telegram_id, limit=10)
    user_messages = [m["content"] for m in messages if m["role"] == "user"]
    if not user_messages:
        return

    text_block = "\n---\n".join(user_messages[-5:])

    try:
        response = await _haiku_client.messages.create(
            model=CLAUDE_MODEL_FAST,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"""Проанализируй последние сообщения пользователя в коучинговом диалоге. Выяви паттерны поведения из списка:
- weak_commitment: слабые обязательства, избегание конкретики
- blame_external: перекладывание ответственности на других
- low_self_worth: самообесценивание, неверие в себя
- avoidance: уход от темы, смена темы
- seeking_pity: поиск жалости вместо решений
- vague: размытые формулировки без конкретики
- not_ready: паттерн "ещё не готов/не время"

Сообщения:
{text_block}

Верни ТОЛЬКО JSON массив найденных паттернов (может быть пустым):
[{{"type": "pattern_type", "text": "краткое описание на русском"}}]"""
            }],
        )

        result_text = response.content[0].text.strip()
        # Try to extract JSON from response
        if "[" in result_text:
            json_str = result_text[result_text.index("["):result_text.rindex("]")+1]
            patterns = json.loads(json_str)
            for p in patterns:
                if "type" in p and "text" in p:
                    await add_pattern(
                        telegram_id=telegram_id,
                        pattern_type=p["type"],
                        pattern_text=p["text"],
                    )
    except Exception:
        pass  # Non-critical, don't break the flow
