"""
Валидация Telegram initData по HMAC-SHA256.
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import parse_qs

from shared.config import TELEGRAM_BOT_TOKEN

# initData действителен 1 час
MAX_AGE_SECONDS = 3600


def validate_init_data(init_data: str) -> Optional[dict]:
    """
    Проверяет подпись initData от Telegram.
    Возвращает dict с данными пользователя или None если невалидно.
    """
    if not init_data or not TELEGRAM_BOT_TOKEN:
        return None

    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
    except Exception:
        return None

    received_hash = parsed.get("hash", [None])[0]
    if not received_hash:
        return None

    # Проверяем auth_date
    auth_date_str = parsed.get("auth_date", [None])[0]
    if not auth_date_str:
        return None
    try:
        auth_date = int(auth_date_str)
    except ValueError:
        return None
    if time.time() - auth_date > MAX_AGE_SECONDS:
        return None

    # Собираем data-check-string: все поля кроме hash, отсортированные по ключу
    check_pairs = []
    for key in sorted(parsed.keys()):
        if key == "hash":
            continue
        check_pairs.append(f"{key}={parsed[key][0]}")
    data_check_string = "\n".join(check_pairs)

    # secret_key = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData", TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256
    ).digest()

    # calculated_hash = HMAC-SHA256(secret_key, data_check_string)
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    # Парсим user из initData
    user_str = parsed.get("user", [None])[0]
    if not user_str:
        return None

    try:
        user_data = json.loads(user_str)
    except (json.JSONDecodeError, TypeError):
        return None

    return {
        "telegram_id": user_data.get("id"),
        "first_name": user_data.get("first_name", ""),
        "last_name": user_data.get("last_name", ""),
        "username": user_data.get("username", ""),
        "photo_url": user_data.get("photo_url", ""),
        "auth_date": auth_date,
    }
