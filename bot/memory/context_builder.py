from bot.memory.database import get_recent_messages, get_patterns
from bot.prompts.system_prompt import build_system_prompt


async def build_context(user: dict) -> tuple[str, list[dict]]:
    """
    Возвращает (system_prompt, messages_history) для запроса к Claude.
    """
    patterns = await get_patterns(user["telegram_id"])
    system_prompt = build_system_prompt(user, patterns, mode=user.get("mode", "coaching"))
    messages = await get_recent_messages(user["telegram_id"], limit=20)
    return system_prompt, messages
