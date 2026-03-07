#!/bin/bash
# Ежедневный анализ качества Евы
# Запуск: launchd или вручную ./scripts/daily_quality.sh

set -e

PROJECT_DIR="/Users/yaroslavsorokin/Desktop/ai_nastavnik"
RAILWAY_URL="https://eva-bot-production.up.railway.app"
DB_PATH="/tmp/nastavnik_analysis.db"
SESSIONS_PATH="/tmp/sessions.json"

# Загрузить nvm (claude установлен через npm)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

# Загрузить переменные из .env
set -a
source "$PROJECT_DIR/.env"
set +a

echo "[$(date)] Starting quality analysis..."

# 1. Скачать БД с Railway
echo "Downloading DB..."
curl --fail -s -o "$DB_PATH" "$RAILWAY_URL/api/admin/db?key=$ADMIN_KEY"
if [ $? -ne 0 ] || [ ! -s "$DB_PATH" ]; then
    echo "ERROR: Failed to download DB (HTTP error or empty file)"
    exit 1
fi
# Проверить что это SQLite
if ! sqlite3 "$DB_PATH" "SELECT 1" >/dev/null 2>&1; then
    echo "ERROR: Downloaded file is not a valid SQLite database"
    exit 1
fi

# 2. Извлечь сессии
echo "Extracting sessions..."
python3 "$PROJECT_DIR/scripts/extract_sessions.py" "$DB_PATH" "$SESSIONS_PATH"

# 3. Проверить есть ли данные
USERS=$(python3 -c "import json; d=json.load(open('$SESSIONS_PATH')); print(len(d['users']))")
if [ "$USERS" = "0" ]; then
    echo "No activity yesterday. Skipping analysis."
    printf '\n---\n\n## Отчет за %s\n\nНет активности.\n' "$(date -v-1d +%Y-%m-%d)" >> "$PROJECT_DIR/docs/quality_reports.md"
    exit 0
fi

# 4. Запустить Claude Code для анализа
if ! command -v claude &>/dev/null; then
    echo "ERROR: claude CLI not found. Install: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

echo "Running Claude analysis ($USERS users)..."
cd "$PROJECT_DIR"
claude -p "$(cat scripts/quality_prompt.md)" --allowedTools "Read,Write" --permission-mode acceptEdits --max-turns 10

echo "[$(date)] Done! Report appended to docs/quality_reports.md"
