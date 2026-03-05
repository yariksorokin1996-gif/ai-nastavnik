"""Мониторинг аномалий с дедупликацией алертов."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.config import ALERT_THRESHOLDS, OWNER_TELEGRAM_ID

logger = logging.getLogger(__name__)
MOSCOW_TZ = timezone(timedelta(hours=3))

# Окна дедупликации (секунды) по типу события
_DEDUP_WINDOWS: dict[str, int] = {
    "crisis_level_3": 0,           # без дедупликации
    "latency_critical_ms": 1800,   # 30 мин
    "consecutive_empty_context": 900,  # 15 мин
    "consecutive_errors": 900,     # 15 мин
}


class Alerter:
    def __init__(self) -> None:
        self._bot = None  # telegram.Bot, инициализируется через init()
        self._counters: dict[tuple[int, str], int] = {}
        self._last_alert: dict[tuple[int, str], float] = {}

    def init(self, bot) -> None:
        """Инициализация Telegram-ботом. Вызвать из post_init в main.py."""
        self._bot = bot

    async def check(self, telegram_id: int, event: str, value: Any = None) -> None:
        """Проверяет порог и отправляет алерт если превышен."""
        threshold = ALERT_THRESHOLDS.get(event)
        if threshold is None:
            logger.warning("Unknown alert event: %s", event)
            return

        # Для latency — сравнение value с порогом (не счётчик)
        if event == "latency_critical_ms":
            if value is not None and value > threshold:
                await self._maybe_send(telegram_id, event, value)
            return

        # Для crisis_level_3 — мгновенный алерт (порог=1, без инкремента)
        if event == "crisis_level_3":
            await self._maybe_send(telegram_id, event, value)
            return

        # Для остальных — инкрементируемые счётчики
        key = (telegram_id, event)
        self._counters[key] = self._counters.get(key, 0) + 1
        if self._counters[key] >= threshold:
            await self._maybe_send(telegram_id, event, value)
            self._counters[key] = 0  # auto-reset

    def reset(self, telegram_id: int, event: str) -> None:
        """Сброс счётчика (вызывать при успехе)."""
        key = (telegram_id, event)
        self._counters.pop(key, None)

    async def _maybe_send(self, telegram_id: int, event: str, value: Any) -> None:
        """Проверяет дедупликацию и отправляет алерт."""
        key = (telegram_id, event)
        now = time.monotonic()
        window = _DEDUP_WINDOWS.get(event, 300)

        if window > 0:
            last = self._last_alert.get(key)
            if last is not None and now - last < window:
                return

        self._last_alert[key] = now
        now_msk = datetime.now(MOSCOW_TZ).strftime("%H:%M:%S")
        text = f"⚠️ [{event}]\nUser: {telegram_id}\nValue: {value}\nTime: {now_msk}"
        await self._send_alert(text)

    async def _send_alert(self, text: str) -> None:
        """Отправляет алерт в Telegram OWNER_TELEGRAM_ID."""
        if self._bot is None:
            logger.warning("Alerter: bot not initialized, skipping alert")
            return
        if not OWNER_TELEGRAM_ID:
            logger.warning("Alerter: OWNER_TELEGRAM_ID=0, skipping alert")
            return
        try:
            await self._bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=text)
        except Exception:
            logger.error("Alerter: failed to send alert", exc_info=True)


alerter = Alerter()
