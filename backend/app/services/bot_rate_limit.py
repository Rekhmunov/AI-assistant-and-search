"""
Ограничение частоты запросов к MAX Bot API.

Официальный лимит: 30 rps на platform-api.max.ru (dev.max.ru/docs-api).
Держим запас, чтобы не получить 429 и блокировку токена.
"""

from __future__ import annotations

import asyncio
import time

# Официально до 30 rps; рабочий потолок с запасом под пики (рассылки + агенты + webhook).
MAX_API_TARGET_RPS = 22
_MIN_INTERVAL_SEC = 1.0 / MAX_API_TARGET_RPS

_lock = asyncio.Lock()
_last_request_at = 0.0


async def throttle_max_api() -> None:
    """Пауза перед следующим вызовом platform-api.max.ru."""
    global _last_request_at
    async with _lock:
        now = time.monotonic()
        elapsed = now - _last_request_at
        if elapsed < _MIN_INTERVAL_SEC:
            await asyncio.sleep(_MIN_INTERVAL_SEC - elapsed)
        _last_request_at = time.monotonic()
