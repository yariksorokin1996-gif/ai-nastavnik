"""Конфигурация проекта."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

CLAUDE_MODEL = os.getenv('CLAUDE_MODEL_MAIN', 'claude-sonnet-4-5')
GPT_MODEL = os.getenv('GPT_MODEL', 'gpt-4o-mini')
DIALOG_PROVIDER = os.getenv('DIALOG_PROVIDER', 'claude')
DIALOG_GPT_MODEL = os.getenv('DIALOG_GPT_MODEL', 'gpt-4.1-mini')

DB_PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nastavnik.db'))
WEBAPP_URL = os.getenv('WEBAPP_URL', '')

OWNER_TELEGRAM_ID = int(os.getenv('OWNER_TELEGRAM_ID', '0'))
TOKEN_BUDGET_SOFT = 3800
RATE_LIMIT_PER_MINUTE = 60
CLAUDE_TIMEOUT = 30
GPT_TIMEOUT = 15
FALLBACK_RESPONSE = 'Мм, мне нужно немного подумать. Напиши ещё раз через минутку?'
FULL_UPDATE_PAUSE_MINUTES = 30

ADMIN_KEY = os.getenv('ADMIN_KEY', '')

ALERT_THRESHOLDS = {
    'consecutive_empty_context': 3,
    'consecutive_errors': 3,
    'latency_critical_ms': 25000,
    'crisis_level_3': 1,
}
