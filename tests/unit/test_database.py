"""
Тесты для bot/memory/database.py
17 таблиц, ~40 CRUD-функций. Реальная SQLite в tmp_path.
"""

import os
import sys

# Корень проекта в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import aiosqlite
import pytest

from bot.memory.database import (
    add_emotion,
    add_goal_step,
    add_message,
    add_or_increment_pattern,
    add_pending_fact,
    add_webapp_event,
    clear_pending_facts,
    create_daily_message,
    create_episode,
    create_feedback,
    create_goal,
    create_user,
    delete_old_messages,
    delete_old_webapp_events,
    delete_user_completely,
    delete_user_data,
    get_active_goal,
    get_all_users,
    get_episode_headers,
    get_episodes_by_ids,
    get_goal_steps,
    get_messages_since,
    get_patterns,
    get_pending_facts,
    get_procedural,
    get_profile,
    get_profile_version,
    get_recent_emotions,
    get_recent_messages,
    get_running_summary,
    get_user,
    get_users_needing_update,
    init_db,
    is_message_processed,
    mark_daily_responded,
    mark_message_processed,
    retention_cleanup,
    save_running_summary,
    save_weekly_report,
    update_enactment,
    update_feeling,
    update_goal_status,
    update_user,
    upsert_procedural,
    upsert_profile,
)

# ---------------------------------------------------------------------------
# Фикстура: подмена DB_PATH на временный файл
# ---------------------------------------------------------------------------

USER_ID = 100001
USER_ID_2 = 100002
USER_ID_3 = 100003


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Подменяет DB_PATH на временный файл."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr("bot.memory.database.DB_PATH", db_file)
    monkeypatch.setattr("shared.config.DB_PATH", db_file)
    return db_file


# ===========================================================================
# Инфраструктура
# ===========================================================================


@pytest.mark.asyncio
async def test_init_db_creates_18_tables(test_db):
    """init_db() создаёт ровно 18 таблиц."""
    await init_db()
    async with aiosqlite.connect(test_db) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ) as cur:
            tables = [row[0] for row in await cur.fetchall()]
    assert len(tables) == 18, f"Ожидалось 18 таблиц, получено {len(tables)}: {tables}"


@pytest.mark.asyncio
async def test_wal_mode_enabled(test_db):
    """PRAGMA journal_mode возвращает 'wal'."""
    await init_db()
    async with aiosqlite.connect(test_db) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        async with db.execute("PRAGMA journal_mode") as cur:
            row = await cur.fetchone()
    assert row[0] == "wal"


@pytest.mark.asyncio
async def test_foreign_keys_enabled(test_db):
    """PRAGMA foreign_keys возвращает 1 (в get_db)."""
    await init_db()
    # get_db() включает FK при каждом соединении
    from bot.memory.database import get_db

    async with get_db() as db:
        async with db.execute("PRAGMA foreign_keys") as cur:
            row = await cur.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_checkins_table_dropped(test_db):
    """Таблицы checkins нет после init_db()."""
    await init_db()
    async with aiosqlite.connect(test_db) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='checkins'"
        ) as cur:
            row = await cur.fetchone()
    assert row is None, "Таблица checkins должна быть удалена"


# ===========================================================================
# Users CRUD
# ===========================================================================


@pytest.mark.asyncio
async def test_create_user(test_db):
    """create_user возвращает dict с telegram_id."""
    await init_db()
    user = await create_user(USER_ID, name="Маша")
    assert isinstance(user, dict)
    assert user["telegram_id"] == USER_ID
    assert user["name"] == "Маша"


@pytest.mark.asyncio
async def test_create_user_duplicate(test_db):
    """INSERT OR IGNORE не ломается при дубле."""
    await init_db()
    u1 = await create_user(USER_ID, name="Маша")
    u2 = await create_user(USER_ID, name="Другое имя")
    # Дубль игнорируется, имя не меняется
    assert u1["telegram_id"] == u2["telegram_id"]
    assert u2["name"] == "Маша"


@pytest.mark.asyncio
async def test_get_user_not_found(test_db):
    """get_user для несуществующего = None."""
    await init_db()
    result = await get_user(999999)
    assert result is None


@pytest.mark.asyncio
async def test_update_user(test_db):
    """Обновление полей, проверка updated_at."""
    await init_db()
    await create_user(USER_ID, name="Маша")
    original = await get_user(USER_ID)
    old_updated = original["updated_at"]

    await update_user(USER_ID, name="Новое имя")
    updated = await get_user(USER_ID)

    assert updated["name"] == "Новое имя"
    assert updated["updated_at"] >= old_updated


@pytest.mark.asyncio
async def test_update_user_bad_field(test_db):
    """ValueError при неизвестном поле."""
    await init_db()
    await create_user(USER_ID)
    with pytest.raises(ValueError, match="недопустимые поля"):
        await update_user(USER_ID, nonexistent_field="value")


@pytest.mark.asyncio
async def test_get_all_users(test_db):
    """Создать 3 пользователей, получить 3."""
    await init_db()
    await create_user(USER_ID, name="А")
    await create_user(USER_ID_2, name="Б")
    await create_user(USER_ID_3, name="В")
    users = await get_all_users()
    assert len(users) == 3


@pytest.mark.asyncio
async def test_get_users_needing_update(test_db):
    """Только пользователи с needs_full_update=1 и last_message_at > 30 мин назад."""
    await init_db()

    # Пользователь 1: needs_full_update=1, last_message_at давно (подходит)
    await create_user(USER_ID, name="Нужен")
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            "UPDATE users SET needs_full_update=1, last_message_at=datetime('now', '-2 hours') WHERE telegram_id=?",
            (USER_ID,),
        )
        await db.commit()

    # Пользователь 2: needs_full_update=0 (не подходит)
    await create_user(USER_ID_2, name="Не нужен")

    # Пользователь 3: needs_full_update=1, но last_message_at только что (не подходит)
    await create_user(USER_ID_3, name="Свежий")
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            "UPDATE users SET needs_full_update=1, last_message_at=datetime('now') WHERE telegram_id=?",
            (USER_ID_3,),
        )
        await db.commit()

    result = await get_users_needing_update()
    assert result == [USER_ID]


# ===========================================================================
# Running Summary
# ===========================================================================


@pytest.mark.asyncio
async def test_get_running_summary_empty(test_db):
    """get_running_summary для нового юзера возвращает пустую строку."""
    await init_db()
    await create_user(USER_ID, name="Маша")
    result = await get_running_summary(USER_ID)
    assert result == ""


@pytest.mark.asyncio
async def test_save_and_get_running_summary(test_db):
    """save_running_summary сохраняет текст, get_running_summary читает."""
    await init_db()
    await create_user(USER_ID, name="Маша")
    summary_text = "ФАКТЫ: Маша, 28 лет, живёт в Москве.\nЭМОЦИИ: тревога."
    await save_running_summary(USER_ID, summary_text)
    result = await get_running_summary(USER_ID)
    assert result == summary_text


@pytest.mark.asyncio
async def test_get_running_summary_not_found(test_db):
    """get_running_summary для несуществующего юзера возвращает пустую строку."""
    await init_db()
    result = await get_running_summary(999999)
    assert result == ""


# ===========================================================================
# Messages CRUD
# ===========================================================================


@pytest.mark.asyncio
async def test_add_message_returns_id(test_db):
    """add_message возвращает int > 0."""
    await init_db()
    await create_user(USER_ID)
    msg_id = await add_message(USER_ID, "user", "Привет!")
    assert isinstance(msg_id, int)
    assert msg_id > 0


@pytest.mark.asyncio
async def test_get_recent_messages_order(test_db):
    """Последние N сообщений в хронологическом порядке."""
    await init_db()
    await create_user(USER_ID)
    id1 = await add_message(USER_ID, "user", "Первое")
    id2 = await add_message(USER_ID, "assistant", "Второе")
    id3 = await add_message(USER_ID, "user", "Третье")

    msgs = await get_recent_messages(USER_ID, limit=3)
    assert len(msgs) == 3
    # Хронологический порядок: от старого к новому
    assert msgs[0]["id"] == id1
    assert msgs[1]["id"] == id2
    assert msgs[2]["id"] == id3


@pytest.mark.asyncio
async def test_get_messages_since(test_db):
    """Фильтрация сообщений по дате."""
    await init_db()
    await create_user(USER_ID)

    # Вставляем через SQL с искусственными датами
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            "INSERT INTO messages (telegram_id, role, content, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (USER_ID, "user", "Старое", "user", "2020-01-01 00:00:00"),
        )
        await db.execute(
            "INSERT INTO messages (telegram_id, role, content, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (USER_ID, "user", "Новое", "user", "2026-06-01 00:00:00"),
        )
        await db.commit()

    msgs = await get_messages_since(USER_ID, "2025-01-01 00:00:00")
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Новое"


@pytest.mark.asyncio
async def test_delete_old_messages(test_db):
    """Retention: удаление старых сообщений."""
    await init_db()
    await create_user(USER_ID)

    async with aiosqlite.connect(test_db) as db:
        # Очень старое сообщение
        await db.execute(
            "INSERT INTO messages (telegram_id, role, content, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (USER_ID, "user", "Древнее", "user", "2020-01-01 00:00:00"),
        )
        # Свежее сообщение
        await db.execute(
            "INSERT INTO messages (telegram_id, role, content, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (USER_ID, "user", "Свежее", "user", "2099-01-01 00:00:00"),
        )
        await db.commit()

    await delete_old_messages(days=1)

    async with aiosqlite.connect(test_db) as db:
        async with db.execute("SELECT content FROM messages WHERE telegram_id=?", (USER_ID,)) as cur:
            rows = await cur.fetchall()
    contents = [r[0] for r in rows]
    assert "Древнее" not in contents
    assert "Свежее" in contents


# ===========================================================================
# Idempotency
# ===========================================================================


@pytest.mark.asyncio
async def test_is_message_processed_false(test_db):
    """Новый message_id -> False."""
    await init_db()
    result = await is_message_processed(999999)
    assert result is False


@pytest.mark.asyncio
async def test_mark_and_check_processed(test_db):
    """mark -> check -> True."""
    await init_db()
    msg_id = 42
    await mark_message_processed(msg_id, USER_ID)
    result = await is_message_processed(msg_id)
    assert result is True


# ===========================================================================
# Profiles
# ===========================================================================


@pytest.mark.asyncio
async def test_get_profile_none(test_db):
    """None для нового юзера (нет записи в semantic_profiles)."""
    await init_db()
    await create_user(USER_ID)
    result = await get_profile(USER_ID)
    assert result is None


@pytest.mark.asyncio
async def test_upsert_profile_creates(test_db):
    """Первый upsert создаёт запись с version=1."""
    await init_db()
    await create_user(USER_ID)
    await upsert_profile(USER_ID, {"key": "value"}, tokens_count=100)
    profile = await get_profile(USER_ID)
    assert profile is not None
    assert profile["version"] == 1


@pytest.mark.asyncio
async def test_upsert_profile_increments_version(test_db):
    """Второй upsert -> version=2."""
    await init_db()
    await create_user(USER_ID)
    await upsert_profile(USER_ID, {"v": 1}, tokens_count=100)
    await upsert_profile(USER_ID, {"v": 2}, tokens_count=200)
    profile = await get_profile(USER_ID)
    assert profile["version"] == 2


@pytest.mark.asyncio
async def test_upsert_profile_saves_to_versions(test_db):
    """profile_versions содержит обе записи."""
    await init_db()
    await create_user(USER_ID)
    await upsert_profile(USER_ID, {"v": 1}, tokens_count=100)
    await upsert_profile(USER_ID, {"v": 2}, tokens_count=200)

    async with aiosqlite.connect(test_db) as db:
        async with db.execute(
            "SELECT version FROM profile_versions WHERE telegram_id=? ORDER BY version",
            (USER_ID,),
        ) as cur:
            versions = [row[0] for row in await cur.fetchall()]
    assert versions == [1, 2]


@pytest.mark.asyncio
async def test_get_profile_parses_json(test_db):
    """profile_json возвращается как dict, не строка."""
    await init_db()
    await create_user(USER_ID)
    data = {"name": "Маша", "values": [1, 2, 3]}
    await upsert_profile(USER_ID, data, tokens_count=50)
    profile = await get_profile(USER_ID)
    assert isinstance(profile["profile_json"], dict)
    assert profile["profile_json"] == data


# ===========================================================================
# Episodes
# ===========================================================================


@pytest.mark.asyncio
async def test_create_episode(test_db):
    """create_episode возвращает id."""
    await init_db()
    await create_user(USER_ID)
    ep_id = await create_episode(
        USER_ID,
        title="Первый разговор",
        summary="Знакомство",
    )
    assert isinstance(ep_id, int)
    assert ep_id > 0


@pytest.mark.asyncio
async def test_get_episode_headers(test_db):
    """Только id, title, created_at."""
    await init_db()
    await create_user(USER_ID)
    await create_episode(USER_ID, title="Эпизод 1", summary="Первый")
    await create_episode(USER_ID, title="Эпизод 2", summary="Второй")

    headers = await get_episode_headers(USER_ID)
    assert len(headers) == 2
    # Проверяем, что только 3 ключа
    for h in headers:
        assert set(h.keys()) == {"id", "title", "created_at"}


@pytest.mark.asyncio
async def test_get_episodes_by_ids(test_db):
    """Загрузка по списку id, commitments_json = list."""
    await init_db()
    await create_user(USER_ID)
    id1 = await create_episode(
        USER_ID,
        title="Ep1",
        summary="S1",
        commitments_json=["делать зарядку", "читать"],
    )
    id2 = await create_episode(USER_ID, title="Ep2", summary="S2")

    episodes = await get_episodes_by_ids([id1, id2])
    assert len(episodes) == 2
    for ep in episodes:
        assert isinstance(ep["commitments_json"], list)
    # У первого эпизода — непустой список
    ep1 = next(e for e in episodes if e["id"] == id1)
    assert ep1["commitments_json"] == ["делать зарядку", "читать"]


# ===========================================================================
# Procedural memory
# ===========================================================================


@pytest.mark.asyncio
async def test_upsert_procedural(test_db):
    """Insert + update, memory_json как dict."""
    await init_db()
    await create_user(USER_ID)

    # Insert
    await upsert_procedural(USER_ID, {"style": "warm"}, tokens_count=50)
    result = await get_procedural(USER_ID)
    assert result is not None
    assert isinstance(result["memory_json"], dict)
    assert result["memory_json"]["style"] == "warm"

    # Update
    await upsert_procedural(USER_ID, {"style": "warm", "tone": "soft"}, tokens_count=80)
    result2 = await get_procedural(USER_ID)
    assert result2["memory_json"]["tone"] == "soft"
    assert result2["tokens_count"] == 80


@pytest.mark.asyncio
async def test_get_procedural_none(test_db):
    """None для нового юзера."""
    await init_db()
    await create_user(USER_ID)
    result = await get_procedural(USER_ID)
    assert result is None


# ===========================================================================
# Pending facts
# ===========================================================================


@pytest.mark.asyncio
async def test_add_and_get_pending_facts(test_db):
    """add 2, get 2."""
    await init_db()
    await create_user(USER_ID)
    await add_pending_fact(USER_ID, "name", "Маша")
    await add_pending_fact(USER_ID, "city", "Москва")
    facts = await get_pending_facts(USER_ID)
    assert len(facts) == 2


@pytest.mark.asyncio
async def test_clear_pending_facts(test_db):
    """clear, затем get = []."""
    await init_db()
    await create_user(USER_ID)
    await add_pending_fact(USER_ID, "name", "Маша")
    await clear_pending_facts(USER_ID)
    facts = await get_pending_facts(USER_ID)
    assert facts == []


# ===========================================================================
# Emotion log
# ===========================================================================


@pytest.mark.asyncio
async def test_add_and_get_emotions(test_db):
    """add 3, get_recent(limit=2) = 2."""
    await init_db()
    await create_user(USER_ID)
    await add_emotion(USER_ID, "joy")
    await add_emotion(USER_ID, "sadness")
    await add_emotion(USER_ID, "anger")
    emotions = await get_recent_emotions(USER_ID, limit=2)
    assert len(emotions) == 2


# ===========================================================================
# Patterns
# ===========================================================================


@pytest.mark.asyncio
async def test_add_pattern_new(test_db):
    """Новый паттерн, count=1."""
    await init_db()
    await create_user(USER_ID)
    await add_or_increment_pattern(USER_ID, "avoidance", "избегание конфликтов")
    patterns = await get_patterns(USER_ID)
    assert len(patterns) == 1
    assert patterns[0]["count"] == 1


@pytest.mark.asyncio
async def test_add_pattern_increment(test_db):
    """Повторный вызов -> count=2."""
    await init_db()
    await create_user(USER_ID)
    await add_or_increment_pattern(USER_ID, "avoidance", "избегание конфликтов")
    await add_or_increment_pattern(USER_ID, "avoidance", "избегание конфликтов")
    patterns = await get_patterns(USER_ID)
    assert len(patterns) == 1
    assert patterns[0]["count"] == 2


# ===========================================================================
# Goals + steps
# ===========================================================================


@pytest.mark.asyncio
async def test_create_and_get_active_goal(test_db):
    """create -> get_active -> match."""
    await init_db()
    await create_user(USER_ID)
    goal_id = await create_goal(USER_ID, "Научиться медитировать")
    active = await get_active_goal(USER_ID)
    assert active is not None
    assert active["id"] == goal_id
    assert active["title"] == "Научиться медитировать"
    assert active["status"] == "active"


@pytest.mark.asyncio
async def test_update_goal_status(test_db):
    """active -> completed."""
    await init_db()
    await create_user(USER_ID)
    goal_id = await create_goal(USER_ID, "Цель")
    await update_goal_status(goal_id, status="completed", completed_at="2026-03-03 12:00:00")
    active = await get_active_goal(USER_ID)
    # После завершения активных целей нет
    assert active is None

    async with aiosqlite.connect(test_db) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM goals WHERE id=?", (goal_id,)) as cur:
            row = await cur.fetchone()
    assert dict(row)["status"] == "completed"


@pytest.mark.asyncio
async def test_goal_steps_order(test_db):
    """3 шага с sort_order, проверить порядок."""
    await init_db()
    await create_user(USER_ID)
    goal_id = await create_goal(USER_ID, "Цель")

    await add_goal_step(goal_id, USER_ID, "Шаг C", sort_order=3)
    await add_goal_step(goal_id, USER_ID, "Шаг A", sort_order=1)
    await add_goal_step(goal_id, USER_ID, "Шаг B", sort_order=2)

    steps = await get_goal_steps(goal_id)
    assert len(steps) == 3
    assert steps[0]["title"] == "Шаг A"
    assert steps[1]["title"] == "Шаг B"
    assert steps[2]["title"] == "Шаг C"


# ===========================================================================
# Daily messages
# ===========================================================================


@pytest.mark.asyncio
async def test_create_daily_message(test_db):
    """id > 0."""
    await init_db()
    await create_user(USER_ID)
    dm_id = await create_daily_message(USER_ID, "Доброе утро!", day_number=1)
    assert isinstance(dm_id, int)
    assert dm_id > 0


@pytest.mark.asyncio
async def test_mark_daily_responded(test_db):
    """responded=1 после mark."""
    await init_db()
    await create_user(USER_ID)
    dm_id = await create_daily_message(USER_ID, "Доброе утро!", day_number=1)
    await mark_daily_responded(dm_id, response_delay_minutes=15)

    async with aiosqlite.connect(test_db) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM daily_messages WHERE id=?", (dm_id,)) as cur:
            row = await cur.fetchone()
    assert dict(row)["responded"] == 1
    assert dict(row)["response_delay_minutes"] == 15


# ===========================================================================
# Feedback
# ===========================================================================


@pytest.mark.asyncio
async def test_create_and_update_feedback(test_db):
    """create + update_feeling + update_enactment."""
    await init_db()
    await create_user(USER_ID)
    ep_id = await create_episode(USER_ID, title="Ep", summary="S")
    fb_id = await create_feedback(USER_ID, ep_id, session_end="2026-03-03 12:00:00", messages_in_session=10)
    assert fb_id > 0

    await update_feeling(fb_id, feeling_after=4)
    await update_enactment(fb_id, tried_in_practice=1)

    async with aiosqlite.connect(test_db) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM session_feedback WHERE id=?", (fb_id,)) as cur:
            row = await cur.fetchone()
    data = dict(row)
    assert data["feeling_after"] == 4
    assert data["tried_in_practice"] == 1


# ===========================================================================
# Analytics
# ===========================================================================


@pytest.mark.asyncio
async def test_save_weekly_report(test_db):
    """insert не ломается."""
    await init_db()
    await save_weekly_report(
        week_start="2026-02-24",
        week_end="2026-03-02",
        report_json={"total_users": 10, "messages": 500},
    )
    async with aiosqlite.connect(test_db) as db:
        async with db.execute("SELECT COUNT(*) FROM analytics_weekly") as cur:
            count = (await cur.fetchone())[0]
    assert count == 1


# ===========================================================================
# Webapp events
# ===========================================================================


@pytest.mark.asyncio
async def test_add_and_delete_webapp_events(test_db):
    """add + retention."""
    await init_db()
    await create_user(USER_ID)
    await add_webapp_event(USER_ID, event_type="page_view", page="/home")

    # Вставляем старое событие через SQL
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            "INSERT INTO webapp_events (telegram_id, event_type, page, created_at) VALUES (?, ?, ?, ?)",
            (USER_ID, "page_view", "/old", "2020-01-01 00:00:00"),
        )
        await db.commit()

    await delete_old_webapp_events(days=1)

    async with aiosqlite.connect(test_db) as db:
        async with db.execute("SELECT page FROM webapp_events WHERE telegram_id=?", (USER_ID,)) as cur:
            pages = [row[0] for row in await cur.fetchall()]
    assert "/old" not in pages
    assert "/home" in pages


# ===========================================================================
# Retention
# ===========================================================================


@pytest.mark.asyncio
async def test_retention_cleanup(test_db):
    """Вызов retention_cleanup не ломается."""
    await init_db()
    await create_user(USER_ID)
    # Просто проверяем, что не бросает исключений
    await retention_cleanup(msg_days=90, events_days=90)


# ===========================================================================
# Патч 9.0 — get_profile_version, techniques в episodes
# ===========================================================================


@pytest.mark.asyncio
async def test_get_profile_version(test_db):
    """upsert_profile 2 раза, get_profile_version(version=1) возвращает первую версию."""
    await init_db()
    await create_user(USER_ID)

    profile_v1 = {"name": "Маша", "city": "Москва"}
    profile_v2 = {"name": "Маша", "city": "Питер", "age": 30}

    await upsert_profile(USER_ID, profile_v1, tokens_count=50)
    await upsert_profile(USER_ID, profile_v2, tokens_count=80)

    # Текущий профиль — v2
    current = await get_profile(USER_ID)
    assert current["version"] == 2

    # Версия 1 — первая
    v1 = await get_profile_version(USER_ID, version=1)
    assert v1 is not None
    assert v1 == profile_v1

    # Несуществующая версия — None
    v99 = await get_profile_version(USER_ID, version=99)
    assert v99 is None


@pytest.mark.asyncio
async def test_create_episode_with_techniques(test_db):
    """create_episode с techniques_worked_json и techniques_failed_json сохраняет данные."""
    await init_db()
    await create_user(USER_ID)

    techniques_worked = ["отражение слов", "валидация"]
    techniques_failed = ["давление на действие"]

    ep_id = await create_episode(
        USER_ID,
        title="Тест техник",
        summary="Проверка сохранения техник",
        techniques_worked_json=techniques_worked,
        techniques_failed_json=techniques_failed,
    )
    assert ep_id > 0

    # Проверяем через raw SQL
    async with aiosqlite.connect(test_db) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM episodes WHERE id=?", (ep_id,)) as cur:
            row = await cur.fetchone()
    data = dict(row)

    import json
    assert json.loads(data["techniques_worked_json"]) == techniques_worked
    assert json.loads(data["techniques_failed_json"]) == techniques_failed


@pytest.mark.asyncio
async def test_get_episodes_by_ids_parses_techniques(test_db):
    """get_episodes_by_ids парсит techniques_worked_json и techniques_failed_json как list."""
    await init_db()
    await create_user(USER_ID)

    techniques_worked = ["мягкий вызов", "отражение"]
    techniques_failed = ["два вопроса подряд"]

    ep_id = await create_episode(
        USER_ID,
        title="Техники",
        summary="Проверка парсинга",
        techniques_worked_json=techniques_worked,
        techniques_failed_json=techniques_failed,
    )

    episodes = await get_episodes_by_ids([ep_id])
    assert len(episodes) == 1

    ep = episodes[0]
    assert isinstance(ep["techniques_worked_json"], list)
    assert isinstance(ep["techniques_failed_json"], list)
    assert ep["techniques_worked_json"] == techniques_worked
    assert ep["techniques_failed_json"] == techniques_failed


# ===========================================================================
# Удаление данных пользователя
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_user_data_keeps_user(test_db):
    """delete_user_data удаляет профиль, но сохраняет user и messages."""
    await init_db()
    await create_user(USER_ID, name="Маша")
    await upsert_profile(USER_ID, {"key": "value"}, tokens_count=100)
    await add_message(USER_ID, "user", "Привет!")
    await add_message(USER_ID, "assistant", "Привет, Маша!")

    await delete_user_data(USER_ID)

    # Пользователь остался
    user = await get_user(USER_ID)
    assert user is not None
    assert user["telegram_id"] == USER_ID

    # Профиль удалён
    profile = await get_profile(USER_ID)
    assert profile is None

    # Сообщения остались
    msgs = await get_recent_messages(USER_ID, limit=10)
    assert len(msgs) == 2


@pytest.mark.asyncio
async def test_delete_user_data_resets_counters(test_db):
    """После delete_user_data: current_phase='ЗНАКОМСТВО', messages_total=0."""
    await init_db()
    await create_user(USER_ID, name="Маша")
    await update_user(USER_ID, current_phase="ЗЕРКАЛО", messages_total=42)

    await delete_user_data(USER_ID)

    user = await get_user(USER_ID)
    assert user["current_phase"] == "ЗНАКОМСТВО"
    assert user["messages_total"] == 0
    assert user["needs_full_update"] == 0
    assert user["last_full_update_at"] is None


@pytest.mark.asyncio
async def test_delete_user_completely(test_db):
    """delete_user_completely удаляет всё, включая запись в users."""
    await init_db()
    await create_user(USER_ID, name="Маша")
    await add_message(USER_ID, "user", "Привет!")
    await mark_message_processed(12345, USER_ID)
    await upsert_profile(USER_ID, {"key": "value"}, tokens_count=100)

    await delete_user_completely(USER_ID)

    # Пользователь удалён
    user = await get_user(USER_ID)
    assert user is None

    # Сообщения удалены
    msgs = await get_recent_messages(USER_ID, limit=10)
    assert len(msgs) == 0

    # Processed messages удалены
    assert await is_message_processed(12345) is False
