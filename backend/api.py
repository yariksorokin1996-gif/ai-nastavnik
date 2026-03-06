"""
FastAPI бэкенд для Mini App.
Работает с той же БД (nastavnik.db) через bot.memory.database.
"""
import logging
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.auth import validate_init_data
from bot.goal_manager import (
    _get_step_by_id,
    complete_step,
    get_today_steps,
    skip_step,
)
from bot.memory.database import (
    add_webapp_event,
    create_daily_message,
    create_user,
    delete_user_completely,
    get_active_goal,
    get_db,
    get_goal_steps,
    get_patterns,
    get_user,
    init_db,
)
from bot.memory.profile_manager import get_profile
from bot.prompts.memory_prompts import AFFIRMATION_BANK, AFFIRMATION_PROMPT
from shared.llm_client import LLMError, call_gpt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Uptime tracking
# ---------------------------------------------------------------------------
_START_TIME = time.monotonic()

# ---------------------------------------------------------------------------
# Rate limiting (in-memory)
# ---------------------------------------------------------------------------
_rate_limits: dict[int, list[float]] = {}
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 60  # requests per window


def _check_rate_limit(telegram_id: int) -> None:
    """Проверить rate limit. Raises HTTPException(429) если превышен."""
    now = time.monotonic()
    timestamps = _rate_limits.get(telegram_id, [])

    # Очистить старые записи
    cutoff = now - _RATE_LIMIT_WINDOW
    timestamps = [t for t in timestamps if t > cutoff]

    if len(timestamps) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": "60"},
        )

    timestamps.append(now)
    _rate_limits[telegram_id] = timestamps


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Backend API: БД инициализирована")
    yield


app = FastAPI(title="AI Наставник API", lifespan=lifespan)

# CORS: allow_origins=["*"] допустим для Telegram Mini App.
# Auth идёт через initData HMAC (не cookies), поэтому CSRF невозможен.
# Все мутирующие endpoints защищены Depends(get_telegram_user).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def get_telegram_user(authorization: str = Header(None)) -> dict:
    """Извлекает и валидирует telegram user из заголовка Authorization."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    init_data = authorization.removeprefix("tma ").removeprefix("Bearer ")
    user_data = validate_init_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid initData")

    return user_data


async def rate_limit(tg: dict = Depends(get_telegram_user)) -> dict:
    """Auth + rate limiting dependency."""
    _check_rate_limit(tg["telegram_id"])
    return tg


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    telegram_id: int
    name: Optional[str] = None
    phase: str
    sessions_count: int


class PatternResponse(BaseModel):
    pattern_type: str
    pattern_text: Optional[str] = None
    count: int


class StepResponse(BaseModel):
    id: int
    title: str
    status: str
    deadline_at: Optional[str] = None
    completed_at: Optional[datetime] = None


class GoalResponse(BaseModel):
    id: int
    title: str
    status: str
    steps: list[StepResponse] = Field(default_factory=list)


class GoalsResponse(BaseModel):
    goal: Optional[GoalResponse] = None


class TodayStepsResponse(BaseModel):
    steps: list[StepResponse]
    completed_count: int
    total_count: int


class StepStatusUpdate(BaseModel):
    status: Literal["done", "skipped"]


class CalendarResponse(BaseModel):
    active_days: list[str]
    streak: int
    total_sessions: int


class AffirmationResponse(BaseModel):
    text: str
    source: str


class AnalyticsEventRequest(BaseModel):
    event_type: str
    page: Optional[str] = None
    metadata: Optional[dict] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Healthcheck с проверкой БД и uptime."""
    try:
        async with get_db() as db:
            async with db.execute("SELECT 1") as cur:
                await cur.fetchone()
        db_ok = True
    except Exception:
        db_ok = False

    uptime_s = round(time.monotonic() - _START_TIME, 1)
    status = "ok" if db_ok else "degraded"
    return {"status": status, "db": db_ok, "uptime_s": uptime_s}


@app.get("/api/user", response_model=UserResponse)
async def get_current_user(tg: dict = Depends(rate_limit)):
    """Получить данные текущего пользователя."""
    telegram_id = tg["telegram_id"]

    user = await get_user(telegram_id)
    if not user:
        user = await create_user(telegram_id, tg["first_name"] or "друг")

    return UserResponse(
        telegram_id=user["telegram_id"],
        name=user["name"],
        phase=user["current_phase"],
        sessions_count=user["messages_total"],
    )


@app.get("/api/user/patterns", response_model=list[PatternResponse])
async def get_user_patterns(tg: dict = Depends(rate_limit)):
    """Получить выявленные паттерны пользователя."""
    patterns = await get_patterns(tg["telegram_id"])

    return [
        PatternResponse(
            pattern_type=p["pattern_type"],
            pattern_text=p.get("pattern_text"),
            count=p["count"],
        )
        for p in patterns[:10]
    ]


@app.get("/api/user/goals", response_model=GoalsResponse)
async def get_user_goals(tg: dict = Depends(rate_limit)):
    """Получить активную цель и её шаги."""
    telegram_id = tg["telegram_id"]

    goal = await get_active_goal(telegram_id)
    if not goal:
        return GoalsResponse(goal=None)

    steps_rows = await get_goal_steps(goal["id"])
    steps = [
        StepResponse(
            id=s["id"],
            title=s["title"],
            status=s["status"],
            deadline_at=s.get("deadline_at"),
            completed_at=s.get("completed_at"),
        )
        for s in steps_rows
    ]

    return GoalsResponse(
        goal=GoalResponse(
            id=goal["id"],
            title=goal["title"],
            status=goal["status"],
            steps=steps,
        )
    )


@app.get("/api/user/goals/today", response_model=TodayStepsResponse)
async def get_today_goal_steps(tg: dict = Depends(rate_limit)):
    """Получить шаги с дедлайном на сегодня."""
    telegram_id = tg["telegram_id"]

    today_steps = await get_today_steps(telegram_id)
    step_responses = [
        StepResponse(
            id=s.id,
            title=s.title,
            status=s.status,
            deadline_at=s.deadline_at.strftime("%Y-%m-%d %H:%M:%S") if s.deadline_at else None,
            completed_at=s.completed_at,
        )
        for s in today_steps
    ]
    completed = sum(1 for s in today_steps if s.status == "done")

    return TodayStepsResponse(
        steps=step_responses,
        completed_count=completed,
        total_count=len(today_steps),
    )


@app.put("/api/user/goals/steps/{step_id}")
async def update_step_status_endpoint(
    step_id: int,
    body: StepStatusUpdate,
    tg: dict = Depends(rate_limit),
):
    """Обновить статус шага цели (done/skipped). Owner check."""
    telegram_id = tg["telegram_id"]

    # Owner check
    step = await _get_step_by_id(step_id)
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")
    if step["telegram_id"] != telegram_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        if body.status == "done":
            updated = await complete_step(step_id)
        else:
            updated = await skip_step(step_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StepResponse(
        id=updated.id,
        title=updated.title,
        status=updated.status,
        deadline_at=updated.deadline_at.strftime("%Y-%m-%d %H:%M:%S") if updated.deadline_at else None,
        completed_at=updated.completed_at,
    )


@app.get("/api/user/calendar", response_model=CalendarResponse)
async def get_user_calendar(tg: dict = Depends(rate_limit)):
    """Получить календарь активных дней и streak."""
    telegram_id = tg["telegram_id"]

    # Активные дни за последние 90 дней (по московскому времени +3h)
    async with get_db() as db:
        async with db.execute(
            """SELECT DISTINCT DATE(created_at, '+3 hours') as day
               FROM messages
               WHERE telegram_id = ? AND role = 'user'
                 AND created_at >= date('now', '-90 days')
               ORDER BY day DESC""",
            (telegram_id,),
        ) as cur:
            rows = await cur.fetchall()
            active_days = [row[0] for row in rows]

    # Streak: последовательные дни от сегодня (MSK) назад
    today_msk = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%d")
    streak = 0
    check_date = datetime.strptime(today_msk, "%Y-%m-%d")

    active_days_set = set(active_days)
    for _ in range(90):
        day_str = check_date.strftime("%Y-%m-%d")
        if day_str in active_days_set:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    # total_sessions из users
    user = await get_user(telegram_id)
    total_sessions = user["messages_total"] if user else 0

    return CalendarResponse(
        active_days=active_days,
        streak=streak,
        total_sessions=total_sessions,
    )


@app.get("/api/user/affirmation", response_model=AffirmationResponse)
async def get_affirmation(tg: dict = Depends(rate_limit)):
    """Получить аффирмацию дня. Кеш 24ч в daily_messages(source='affirmation')."""
    telegram_id = tg["telegram_id"]

    # 1. Проверить кеш — есть ли аффирмация на сегодня
    async with get_db() as db:
        async with db.execute(
            """SELECT message_text, source FROM daily_messages
               WHERE telegram_id = ? AND source = 'affirmation'
                 AND DATE(created_at) = DATE('now')
               LIMIT 1""",
            (telegram_id,),
        ) as cur:
            cached = await cur.fetchone()

    if cached:
        return AffirmationResponse(text=cached[0], source=cached[1])

    # 2. Генерация новой аффирмации
    user = await get_user(telegram_id)
    sessions_count = user["messages_total"] if user else 0

    text: str
    source: str

    if sessions_count < 7:
        # Мало данных — берём из банка
        text = random.choice(AFFIRMATION_BANK)
        source = "bank"
    else:
        # Пробуем сгенерировать персональную
        try:
            profile = await get_profile(telegram_id)
            if profile is not None:
                profile_json = profile.model_dump()
                emotional_tone = profile_json.get("emotional_tone", "нейтральный")
                sensitive_topics_list = profile_json.get("sensitive_topics", [])
            else:
                emotional_tone = "нейтральный"
                sensitive_topics_list = []

            sensitive_str = (
                ", ".join(sensitive_topics_list) if sensitive_topics_list else "нет"
            )
            prompt = AFFIRMATION_PROMPT.format(
                emotional_tone=emotional_tone,
                sensitive_topics=sensitive_str,
            )

            text = await call_gpt(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
            )

            # Проверка длины и пустоты
            if not text or len(text) > 200:
                text = random.choice(AFFIRMATION_BANK)
                source = "bank"
            else:
                source = "generated"

        except LLMError:
            text = random.choice(AFFIRMATION_BANK)
            source = "bank"

    # 3. Сохранить в daily_messages
    await create_daily_message(
        telegram_id=telegram_id,
        message_text=text,
        day_number=0,
        source="affirmation",
    )

    return AffirmationResponse(text=text, source=source)


@app.post("/api/analytics/event", status_code=204)
async def track_analytics_event(
    body: AnalyticsEventRequest,
    tg: dict = Depends(rate_limit),
):
    """Сохранить событие аналитики из webapp."""
    await add_webapp_event(
        telegram_id=tg["telegram_id"],
        event_type=body.event_type,
        page=body.page,
        metadata=body.metadata,
    )
    return Response(status_code=204)


@app.delete("/api/user")
async def delete_user(tg: dict = Depends(rate_limit)):
    """Удалить все данные пользователя."""
    await delete_user_completely(tg["telegram_id"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin: скачивание БД для анализа переписок
# ---------------------------------------------------------------------------

@app.get("/api/admin/db")
async def download_db(key: str = ""):
    """Отдаёт файл БД целиком. Защита по ADMIN_KEY."""
    from shared.config import ADMIN_KEY, DB_PATH as _DB_PATH
    if not ADMIN_KEY or key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    db_path = Path(_DB_PATH)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="DB not found")
    return FileResponse(
        path=str(db_path),
        filename="nastavnik.db",
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Статика Mini App (SPA fallback) — ДОЛЖЕН БЫТЬ ПОСЛЕДНИМ
# ---------------------------------------------------------------------------

WEBAPP_DIST = Path(__file__).resolve().parent.parent / "webapp" / "dist"

if WEBAPP_DIST.is_dir():
    # Статические ассеты (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=WEBAPP_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback — отдаём index.html для всех не-API путей."""
        # Пробуем отдать конкретный файл
        file_path = WEBAPP_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # SPA fallback — index.html без кеша
        return FileResponse(
            WEBAPP_DIST / "index.html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
