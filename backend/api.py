"""
FastAPI бэкенд для Mini App.
Работает с той же БД (nastavnik.db) через bot.memory.database.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.auth import validate_init_data
from bot.memory.database import (
    get_user, create_user, update_user, get_patterns,
    get_recent_messages, init_db,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Backend API: БД инициализирована")
    yield


app = FastAPI(title="AI Наставник API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth dependency ---

def _get_telegram_user(authorization: str = Header(None)):
    """Извлекает и валидирует telegram user из заголовка Authorization."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    init_data = authorization.removeprefix("tma ").removeprefix("Bearer ")
    user_data = validate_init_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid initData")

    return user_data


# --- Models ---

class UserResponse(BaseModel):
    telegram_id: int
    name: Optional[str] = None
    phase: str
    goal: Optional[str] = None
    goal_deadline: Optional[str] = None
    area: Optional[str] = None
    sessions_count: int
    is_premium: bool
    coaching_style: int
    mode: str
    commitments: list
    patterns_detected: list


class PatternResponse(BaseModel):
    pattern_type: str
    pattern_text: Optional[str] = None
    count: int


class DailyResponse(BaseModel):
    commitments: list
    recent_patterns: List[PatternResponse]
    sessions_count: int
    phase: str
    streak: int  # placeholder для будущей логики


class StyleUpdate(BaseModel):
    coaching_style: int


class ModeUpdate(BaseModel):
    mode: str


# --- Endpoints ---

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/user", response_model=UserResponse)
async def get_current_user(authorization: str = Header(None)):
    """Получить данные текущего пользователя."""
    tg = _get_telegram_user(authorization)
    telegram_id = tg["telegram_id"]

    user = await get_user(telegram_id)
    if not user:
        user = await create_user(telegram_id, tg["first_name"] or "друг")

    return UserResponse(
        telegram_id=user["telegram_id"],
        name=user["name"],
        phase=user["phase"],
        goal=user["goal"],
        goal_deadline=user["goal_deadline"],
        area=user["area"],
        sessions_count=user["sessions_count"],
        is_premium=bool(user["is_premium"]),
        coaching_style=user["coaching_style"],
        mode=user["mode"],
        commitments=user.get("commitments", []),
        patterns_detected=user.get("patterns_detected", []),
    )


@app.get("/api/user/patterns", response_model=List[PatternResponse])
async def get_user_patterns(authorization: str = Header(None)):
    """Получить выявленные паттерны пользователя."""
    tg = _get_telegram_user(authorization)
    patterns = await get_patterns(tg["telegram_id"])

    return [
        PatternResponse(
            pattern_type=p["pattern_type"],
            pattern_text=p.get("pattern_text"),
            count=p["count"],
        )
        for p in patterns[:10]
    ]


@app.get("/api/user/daily", response_model=DailyResponse)
async def get_daily_data(authorization: str = Header(None)):
    """Данные для главного экрана: обязательства, паттерны, прогресс."""
    tg = _get_telegram_user(authorization)
    telegram_id = tg["telegram_id"]

    user = await get_user(telegram_id)
    if not user:
        user = await create_user(telegram_id, tg["first_name"] or "друг")

    patterns = await get_patterns(telegram_id)

    return DailyResponse(
        commitments=user.get("commitments", []),
        recent_patterns=[
            PatternResponse(
                pattern_type=p["pattern_type"],
                pattern_text=p.get("pattern_text"),
                count=p["count"],
            )
            for p in patterns[:5]
        ],
        sessions_count=user["sessions_count"],
        phase=user["phase"],
        streak=0,  # TODO: рассчитывать по checkins
    )


@app.put("/api/user/style")
async def update_style(
    body: StyleUpdate,
    authorization: str = Header(None),
):
    """Сменить стиль коучинга из Mini App."""
    tg = _get_telegram_user(authorization)
    if body.coaching_style not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="Style must be 1, 2, or 3")

    await update_user(tg["telegram_id"], coaching_style=body.coaching_style)
    return {"ok": True}


@app.put("/api/user/mode")
async def update_mode(
    body: ModeUpdate,
    authorization: str = Header(None),
):
    """Сменить режим общения из Mini App."""
    tg = _get_telegram_user(authorization)
    allowed = ("coach", "friend", "astrologer")
    if body.mode not in allowed:
        raise HTTPException(status_code=400, detail=f"Mode must be one of {allowed}")

    await update_user(tg["telegram_id"], mode=body.mode)
    return {"ok": True}


# --- Статика Mini App ---

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
