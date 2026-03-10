"""
Тесты для модулей аналитики шага 14:
- bot/analytics/alerter.py (6 тестов)
- bot/analytics/feedback_collector.py (8 тестов)
- bot/analytics/daily_report.py (3 теста)
- bot/analytics/weekly_report.py (3 теста)

Итого: 20 тестов.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

MOSCOW_TZ = timezone(timedelta(hours=3))


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _make_context():
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# 1. test_alerter_threshold_not_reached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerter_threshold_not_reached() -> None:
    """2 check consecutive_errors (порог=3) -> _maybe_send НЕ вызван."""
    from bot.analytics.alerter import Alerter

    a = Alerter()
    a._maybe_send = AsyncMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    a.init(bot)

    await a.check(111, "consecutive_errors")
    await a.check(111, "consecutive_errors")

    a._maybe_send.assert_not_awaited()


# ---------------------------------------------------------------------------
# 2. test_alerter_threshold_reached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerter_threshold_reached() -> None:
    """3 check consecutive_errors (порог=3) -> _maybe_send вызван 1 раз, счётчик сброшен."""
    from bot.analytics.alerter import Alerter

    a = Alerter()
    a._maybe_send = AsyncMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    a.init(bot)

    await a.check(111, "consecutive_errors")
    await a.check(111, "consecutive_errors")
    await a.check(111, "consecutive_errors")

    a._maybe_send.assert_awaited_once()
    # Счётчик сброшен (= 0)
    assert a._counters.get((111, "consecutive_errors"), 0) == 0


# ---------------------------------------------------------------------------
# 3. test_alerter_reset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerter_reset() -> None:
    """2 check + reset + 1 check -> _maybe_send НЕ вызван (счётчик=1)."""
    from bot.analytics.alerter import Alerter

    a = Alerter()
    a._maybe_send = AsyncMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    a.init(bot)

    await a.check(111, "consecutive_errors")
    await a.check(111, "consecutive_errors")
    a.reset(111, "consecutive_errors")
    await a.check(111, "consecutive_errors")

    a._maybe_send.assert_not_awaited()
    assert a._counters.get((111, "consecutive_errors"), 0) == 1


# ---------------------------------------------------------------------------
# 4. test_alerter_crisis_immediate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerter_crisis_immediate() -> None:
    """1 check crisis_level_3 -> _maybe_send вызван мгновенно (без счётчика)."""
    from bot.analytics.alerter import Alerter

    a = Alerter()
    a._maybe_send = AsyncMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    a.init(bot)

    await a.check(111, "crisis_level_3", value="suicide_keyword")

    a._maybe_send.assert_awaited_once()


# ---------------------------------------------------------------------------
# 5. test_alerter_latency_above_threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerter_latency_above_threshold() -> None:
    """check latency_critical_ms value=30000 (>25000) -> _maybe_send вызван."""
    from bot.analytics.alerter import Alerter

    a = Alerter()
    a._maybe_send = AsyncMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    a.init(bot)

    await a.check(111, "latency_critical_ms", value=30000)

    a._maybe_send.assert_awaited_once()


# ---------------------------------------------------------------------------
# 6. test_alerter_bot_none
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerter_bot_none() -> None:
    """_bot=None -> logger.warning, _send_alert не crash."""
    from bot.analytics.alerter import Alerter

    a = Alerter()
    # НЕ вызываем init() -> _bot=None

    # _send_alert не должен падать
    await a._send_alert("test alert text")
    # Просто проверяем отсутствие исключения — тест пройдёт если нет crash


# ---------------------------------------------------------------------------
# 7. test_ask_feeling_all_conditions_met
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.feedback_collector._is_quiet_hours", return_value=False)
@patch("bot.analytics.feedback_collector.database")
@patch("bot.analytics.feedback_collector.get_db")
async def test_ask_feeling_all_conditions_met(
    mock_get_db, mock_database, _mock_quiet
) -> None:
    """episode 3h ago, 5 msgs, no feedback -> bot.send_message вызван."""
    from bot.analytics.feedback_collector import ask_feeling

    now_utc = datetime(2026, 3, 4, 13, 0, 0, tzinfo=timezone.utc)
    session_end = (now_utc - timedelta(hours=3)).isoformat()

    # Мок БД: курсоры для каждого запроса
    mock_conn = AsyncMock()

    # episode query
    episode_cursor = AsyncMock()
    episode_cursor.fetchone = AsyncMock(return_value={
        "created_at": (now_utc - timedelta(hours=3)).isoformat(),
        "session_end": session_end,
        "messages_count": 5,
    })

    # feeling_after check -> None (нет feedback)
    feeling_cursor = AsyncMock()
    feeling_cursor.fetchone = AsyncMock(return_value=None)

    # sent=1 check -> None
    sent_cursor = AsyncMock()
    sent_cursor.fetchone = AsyncMock(return_value=None)

    # user still writing check -> None (не писал)
    writing_cursor = AsyncMock()
    writing_cursor.fetchone = AsyncMock(return_value=None)

    # cooldown check -> None
    cooldown_cursor = AsyncMock()
    cooldown_cursor.fetchone = AsyncMock(return_value={"last_sent": None})

    # Настраиваем mock_conn.execute для возврата нужных курсоров
    execute_results = [
        episode_cursor,
        feeling_cursor,
        sent_cursor,
        writing_cursor,
        cooldown_cursor,
    ]
    call_count = {"n": 0}

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        async def __aenter__(self):
            return self._cursor

        async def __aexit__(self, *args):
            pass

    def _execute_side_effect(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return FakeCtx(execute_results[idx])

    mock_conn.execute = MagicMock(side_effect=_execute_side_effect)

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    mock_database.create_feedback = AsyncMock(return_value=42)
    mock_database.mark_feedback_sent = AsyncMock()

    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await ask_feeling(telegram_id=123, episode_id=1, bot=bot)

    assert result is True
    bot.send_message.assert_awaited_once()
    mock_database.mark_feedback_sent.assert_awaited_once_with(42)


# ---------------------------------------------------------------------------
# 8. test_ask_feeling_too_recent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.feedback_collector._is_quiet_hours", return_value=False)
@patch("bot.analytics.feedback_collector.database")
@patch("bot.analytics.feedback_collector.get_db")
async def test_ask_feeling_too_recent(
    mock_get_db, mock_database, _mock_quiet
) -> None:
    """episode с messages_count < 3 -> return False, send_message НЕ вызван."""
    from bot.analytics.feedback_collector import ask_feeling

    now_utc = datetime(2026, 3, 4, 13, 0, 0, tzinfo=timezone.utc)

    # episode с недостаточным количеством сообщений
    episode_cursor = AsyncMock()
    episode_cursor.fetchone = AsyncMock(return_value={
        "created_at": (now_utc - timedelta(hours=1)).isoformat(),
        "session_end": (now_utc - timedelta(hours=1)).isoformat(),
        "messages_count": 2,  # < 3
    })

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        async def __aenter__(self):
            return self._cursor

        async def __aexit__(self, *args):
            pass

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=FakeCtx(episode_cursor))

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await ask_feeling(telegram_id=123, episode_id=1, bot=bot)

    assert result is False
    bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 9. test_ask_feeling_cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.feedback_collector._is_quiet_hours", return_value=False)
@patch("bot.analytics.feedback_collector.database")
@patch("bot.analytics.feedback_collector.get_db")
async def test_ask_feeling_cooldown(
    mock_get_db, mock_database, _mock_quiet
) -> None:
    """feedback с sent=1 и created_at 4h ago (< 8h cooldown) -> return False."""
    from bot.analytics.feedback_collector import ask_feeling

    now_utc = datetime.now(timezone.utc)
    session_end = (now_utc - timedelta(hours=4)).isoformat()

    # episode
    episode_cursor = AsyncMock()
    episode_cursor.fetchone = AsyncMock(return_value={
        "created_at": (now_utc - timedelta(hours=4)).isoformat(),
        "session_end": session_end,
        "messages_count": 5,
    })

    # feeling_after -> None
    feeling_cursor = AsyncMock()
    feeling_cursor.fetchone = AsyncMock(return_value=None)

    # sent=1 -> None
    sent_cursor = AsyncMock()
    sent_cursor.fetchone = AsyncMock(return_value=None)

    # user still writing -> None
    writing_cursor = AsyncMock()
    writing_cursor.fetchone = AsyncMock(return_value=None)

    # cooldown -> отправлен 4ч назад (< 8ч cooldown)
    cooldown_cursor = AsyncMock()
    cooldown_cursor.fetchone = AsyncMock(return_value={
        "last_sent": (now_utc - timedelta(hours=4)).isoformat(),
    })

    execute_results = [
        episode_cursor,
        feeling_cursor,
        sent_cursor,
        writing_cursor,
        cooldown_cursor,
    ]
    call_count = {"n": 0}

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        async def __aenter__(self):
            return self._cursor

        async def __aexit__(self, *args):
            pass

    def _execute_side_effect(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return FakeCtx(execute_results[idx])

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(side_effect=_execute_side_effect)

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await ask_feeling(telegram_id=123, episode_id=1, bot=bot)

    assert result is False
    bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 10. test_ask_feeling_user_still_writing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.feedback_collector._is_quiet_hours", return_value=False)
@patch("bot.analytics.feedback_collector.database")
@patch("bot.analytics.feedback_collector.get_db")
async def test_ask_feeling_user_still_writing(
    mock_get_db, mock_database, _mock_quiet
) -> None:
    """Есть сообщения после session_end -> return False."""
    from bot.analytics.feedback_collector import ask_feeling

    now_utc = datetime(2026, 3, 4, 13, 0, 0, tzinfo=timezone.utc)
    session_end = (now_utc - timedelta(hours=3)).isoformat()

    # episode
    episode_cursor = AsyncMock()
    episode_cursor.fetchone = AsyncMock(return_value={
        "created_at": (now_utc - timedelta(hours=3)).isoformat(),
        "session_end": session_end,
        "messages_count": 5,
    })

    # feeling_after -> None
    feeling_cursor = AsyncMock()
    feeling_cursor.fetchone = AsyncMock(return_value=None)

    # sent=1 -> None
    sent_cursor = AsyncMock()
    sent_cursor.fetchone = AsyncMock(return_value=None)

    # user still writing -> ЕСТЬ (значит пользователь продолжает писать)
    writing_cursor = AsyncMock()
    writing_cursor.fetchone = AsyncMock(return_value={"id": 1})

    execute_results = [
        episode_cursor,
        feeling_cursor,
        sent_cursor,
        writing_cursor,
    ]
    call_count = {"n": 0}

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        async def __aenter__(self):
            return self._cursor

        async def __aexit__(self, *args):
            pass

    def _execute_side_effect(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return FakeCtx(execute_results[idx])

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(side_effect=_execute_side_effect)

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await ask_feeling(telegram_id=123, episode_id=1, bot=bot)

    assert result is False
    bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 11. test_ask_feeling_telegram_fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.feedback_collector._is_quiet_hours", return_value=False)
@patch("bot.analytics.feedback_collector.database")
@patch("bot.analytics.feedback_collector.get_db")
async def test_ask_feeling_telegram_fail(
    mock_get_db, mock_database, _mock_quiet
) -> None:
    """send_message raises Exception -> return False, mark_feedback_sent НЕ вызван."""
    from bot.analytics.feedback_collector import ask_feeling

    now_utc = datetime(2026, 3, 4, 13, 0, 0, tzinfo=timezone.utc)
    session_end = (now_utc - timedelta(hours=3)).isoformat()

    # Все условия пройдены
    episode_cursor = AsyncMock()
    episode_cursor.fetchone = AsyncMock(return_value={
        "created_at": (now_utc - timedelta(hours=3)).isoformat(),
        "session_end": session_end,
        "messages_count": 5,
    })

    feeling_cursor = AsyncMock()
    feeling_cursor.fetchone = AsyncMock(return_value=None)

    sent_cursor = AsyncMock()
    sent_cursor.fetchone = AsyncMock(return_value=None)

    writing_cursor = AsyncMock()
    writing_cursor.fetchone = AsyncMock(return_value=None)

    cooldown_cursor = AsyncMock()
    cooldown_cursor.fetchone = AsyncMock(return_value={"last_sent": None})

    execute_results = [
        episode_cursor, feeling_cursor, sent_cursor, writing_cursor, cooldown_cursor,
    ]
    call_count = {"n": 0}

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        async def __aenter__(self):
            return self._cursor

        async def __aexit__(self, *args):
            pass

    def _execute_side_effect(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return FakeCtx(execute_results[idx])

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(side_effect=_execute_side_effect)

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    mock_database.create_feedback = AsyncMock(return_value=42)
    mock_database.mark_feedback_sent = AsyncMock()

    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=Exception("Telegram API error"))

    result = await ask_feeling(telegram_id=123, episode_id=1, bot=bot)

    assert result is False
    mock_database.mark_feedback_sent.assert_not_awaited()


# ---------------------------------------------------------------------------
# 12. test_ask_feeling_quiet_hours
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.feedback_collector._is_quiet_hours", return_value=True)
async def test_ask_feeling_quiet_hours(_mock_quiet) -> None:
    """Тихие часы (01:00 MSK) -> return False."""
    from bot.analytics.feedback_collector import ask_feeling

    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await ask_feeling(telegram_id=123, episode_id=1, bot=bot)

    assert result is False
    bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 13. test_ask_enactment_conditions_met
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.feedback_collector._is_quiet_hours", return_value=False)
@patch("bot.analytics.feedback_collector.database")
@patch("bot.analytics.feedback_collector.get_db")
async def test_ask_enactment_conditions_met(
    mock_get_db, mock_database, _mock_quiet
) -> None:
    """episode с commitments 14h ago -> send_message вызван."""
    from bot.analytics.feedback_collector import ask_enactment

    # cooldown check -> нет записей за сегодня
    cooldown_cursor = AsyncMock()
    cooldown_cursor.fetchone = AsyncMock(return_value=None)

    # episode с commitments
    episode_cursor = AsyncMock()
    episode_cursor.fetchone = AsyncMock(return_value={
        "id": 10,
        "commitments_json": json.dumps(["Позвонить маме"]),
    })

    # tried_in_practice check -> None (ещё не спрашивали)
    tried_cursor = AsyncMock()
    tried_cursor.fetchone = AsyncMock(return_value=None)

    # guard: нет существующей feedback-записи для episode
    guard_cursor = AsyncMock()
    guard_cursor.fetchone = AsyncMock(return_value=None)

    execute_results = [cooldown_cursor, episode_cursor, tried_cursor, guard_cursor]
    call_count = {"n": 0}

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        async def __aenter__(self):
            return self._cursor

        async def __aexit__(self, *args):
            pass

    def _execute_side_effect(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return FakeCtx(execute_results[idx])

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(side_effect=_execute_side_effect)

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    mock_database.create_feedback = AsyncMock(return_value=99)
    mock_database.mark_feedback_sent = AsyncMock()

    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await ask_enactment(telegram_id=123, bot=bot)

    assert result is True
    bot.send_message.assert_awaited_once()
    mock_database.mark_feedback_sent.assert_awaited_once_with(99)


# ---------------------------------------------------------------------------
# 14. test_ask_enactment_cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.feedback_collector._is_quiet_hours", return_value=False)
@patch("bot.analytics.feedback_collector.database")
@patch("bot.analytics.feedback_collector.get_db")
async def test_ask_enactment_cooldown(
    mock_get_db, mock_database, _mock_quiet
) -> None:
    """already asked today -> return False."""
    from bot.analytics.feedback_collector import ask_enactment

    # cooldown check -> уже спрашивали сегодня
    cooldown_cursor = AsyncMock()
    cooldown_cursor.fetchone = AsyncMock(return_value={"id": 1})

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        async def __aenter__(self):
            return self._cursor

        async def __aexit__(self, *args):
            pass

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=FakeCtx(cooldown_cursor))

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await ask_enactment(telegram_id=123, bot=bot)

    assert result is False
    bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 15. test_daily_report_all_sections
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.daily_report.get_db")
async def test_daily_report_all_sections(mock_get_db) -> None:
    """Тестовые данные -> текст содержит все emoji-секции."""
    from bot.analytics.daily_report import _build_report

    # Мок: каждый execute возвращает пустой курсор с fetchall / fetchone
    # чтобы _build_report не падал и генерировал текст с нулями

    cursor_mock = AsyncMock()
    cursor_mock.fetchone = AsyncMock(return_value=(0,))
    cursor_mock.fetchall = AsyncMock(return_value=[])

    class FakeCtx:
        async def __aenter__(self):
            return cursor_mock

        async def __aexit__(self, *args):
            pass

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=FakeCtx())

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    text = await _build_report()

    # Проверяем наличие ключевых emoji-маркеров секций
    assert "\U0001f4ca" in text      # header
    assert "\U0001f465" in text      # Активные
    assert "\U0001f4ac" in text      # Сообщений
    assert "\U0001f507" in text      # Молчат
    assert "\U0001f60a" in text      # Настроение
    assert "\U0001f4c8" in text      # Фазы
    assert "\U0001f3af" in text      # Цели
    assert "\U0001f4f1" in text      # Webapp
    assert "\U0001f48c" in text      # Daily
    assert "\u26a1" in text          # Latency
    assert "\U0001f6a8" in text      # Кризисов


# ---------------------------------------------------------------------------
# 16. test_daily_report_empty_db
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.daily_report.get_db")
async def test_daily_report_empty_db(mock_get_db) -> None:
    """Пустая БД -> отчёт с нулями/ошибками, не crash."""
    from bot.analytics.daily_report import _build_report

    cursor_mock = AsyncMock()
    cursor_mock.fetchone = AsyncMock(return_value=(0,))
    cursor_mock.fetchall = AsyncMock(return_value=[])

    class FakeCtx:
        async def __aenter__(self):
            return cursor_mock

        async def __aexit__(self, *args):
            pass

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=FakeCtx())

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    text = await _build_report()

    # Не crash + содержит header
    assert "\U0001f4ca" in text
    assert isinstance(text, str)
    assert len(text) > 10


# ---------------------------------------------------------------------------
# 17. test_daily_report_owner_zero
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.daily_report.OWNER_TELEGRAM_ID", 0)
async def test_daily_report_owner_zero() -> None:
    """OWNER_TELEGRAM_ID=0 -> send_message НЕ вызван."""
    from bot.analytics.daily_report import generate_daily_report

    ctx = _make_context()

    await generate_daily_report(ctx)

    ctx.bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 18. test_weekly_anonymization
# ---------------------------------------------------------------------------


def test_weekly_anonymization() -> None:
    """_anonymize с телефоном + email + people -> всё заменено."""
    from bot.analytics.weekly_report import _anonymize

    text = (
        "Маша написала маме Ольга по телефону +7 999 123-45-67 "
        "и email test@example.com"
    )
    people = [{"name": "Ольга", "relationship": "мама"}]

    result = _anonymize(text, user_name="Маша", people=people)

    assert "Маша" not in result
    assert "Ольга" not in result
    assert "+7 999 123-45-67" not in result
    assert "test@example.com" not in result
    assert "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c" in result
    assert "[\u0411\u043b\u0438\u0437\u043a\u0438\u0439 1]" in result
    assert "[\u0422\u0415\u041b\u0415\u0424\u041e\u041d]" in result
    assert "[EMAIL]" in result


# ---------------------------------------------------------------------------
# 19. test_weekly_name_substitution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.weekly_report.database")
@patch("bot.analytics.weekly_report.get_db")
@patch("bot.analytics.weekly_report.call_gpt", new_callable=AsyncMock)
async def test_weekly_name_substitution(
    mock_gpt, mock_get_db, mock_database
) -> None:
    """Проверить что реальные имена появляются в финальном отчёте после LLM."""
    from bot.analytics.weekly_report import _run_llm_analysis

    # Мок БД: один пользователь "Маша"
    users_cursor = AsyncMock()
    users_cursor.fetchall = AsyncMock(return_value=[
        {"telegram_id": 123, "name": "Маша"},
    ])

    msgs_cursor = AsyncMock()
    msgs_cursor.fetchall = AsyncMock(return_value=[
        {"role": "user", "content": "Привет", "created_at": "2026-03-04T10:00:00"},
        {"role": "assistant", "content": "Привет, Маша!", "created_at": "2026-03-04T10:00:05"},
    ])

    call_count = {"n": 0}

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        async def __aenter__(self):
            return self._cursor

        async def __aexit__(self, *args):
            pass

    def _execute_side_effect(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx == 0:
            return FakeCtx(users_cursor)
        return FakeCtx(msgs_cursor)

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(side_effect=_execute_side_effect)

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    mock_database.get_profile = AsyncMock(return_value=None)

    # LLM возвращает JSON с top_hit и top_fail
    mock_gpt.return_value = json.dumps({
        "sessions": [
            {"top_hit": "Хорошая эмпатия", "top_fail": "Слишком быстрый переход"},
        ],
        "recommendation": "Больше валидации",
    })

    result = await _run_llm_analysis()

    # Результат содержит имя "Маша" в финальном отчёте
    full_text = "\n".join(result)
    assert "Маша" in full_text
    assert "Хорошая эмпатия" in full_text


# ---------------------------------------------------------------------------
# 20. test_weekly_llm_fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.analytics.weekly_report.database")
@patch("bot.analytics.weekly_report.get_db")
async def test_weekly_llm_fallback(mock_get_db, mock_database) -> None:
    """LLMError -> отчёт содержит сообщение об ошибке LLM, но не crash."""
    from bot.analytics.weekly_report import _build_weekly_report

    # retention query
    users_count_cursor = AsyncMock()
    users_count_cursor.fetchone = AsyncMock(return_value=(0,))

    # north star feelings
    feelings_cursor = AsyncMock()
    feelings_cursor.fetchall = AsyncMock(return_value=[])

    call_count = {"n": 0}

    class FakeCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        async def __aenter__(self):
            return self._cursor

        async def __aexit__(self, *args):
            pass

    def _execute_side_effect(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx <= 0:
            return FakeCtx(users_count_cursor)
        return FakeCtx(feelings_cursor)

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(side_effect=_execute_side_effect)

    class FakeDB:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    mock_get_db.return_value = FakeDB()

    mock_database.save_weekly_report = AsyncMock()

    from shared.llm_client import LLMError

    with patch(
        "bot.analytics.weekly_report._run_llm_analysis",
        new_callable=AsyncMock,
        side_effect=LLMError("timeout"),
    ):
        text = await _build_weekly_report()

    assert "LLM" in text
    assert isinstance(text, str)
    # Не crash
    assert len(text) > 10
