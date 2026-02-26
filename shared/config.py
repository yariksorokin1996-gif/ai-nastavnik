import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MORNING_CHECKIN_HOUR = int(os.getenv("MORNING_CHECKIN_HOUR", "8"))
MORNING_CHECKIN_MINUTE = int(os.getenv("MORNING_CHECKIN_MINUTE", "0"))
EVENING_CHECKIN_HOUR = int(os.getenv("EVENING_CHECKIN_HOUR", "21"))
EVENING_CHECKIN_MINUTE = int(os.getenv("EVENING_CHECKIN_MINUTE", "0"))

FREE_SESSIONS_LIMIT = int(os.getenv("FREE_SESSIONS_LIMIT", "5"))

CLAUDE_MODEL_MAIN = os.getenv("CLAUDE_MODEL_MAIN", "claude-sonnet-4-5")
CLAUDE_MODEL_FAST = os.getenv("CLAUDE_MODEL_FAST", "claude-haiku-4-5-20251001")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nastavnik.db")

WEBAPP_URL = os.getenv("WEBAPP_URL", "")
