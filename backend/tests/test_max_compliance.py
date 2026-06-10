"""Тесты соответствия лимитам MAX API."""

from __future__ import annotations

import time

from app.services.bot_message_format import MAX_MESSAGE_TEXT_LIMIT, truncate_max_message_text
from app.services.bot_rate_limit import MAX_API_TARGET_RPS, throttle_max_api


def test_truncate_max_message_text():
    long_text = "а" * (MAX_MESSAGE_TEXT_LIMIT + 100)
    trimmed = truncate_max_message_text(long_text)
    assert len(trimmed) <= MAX_MESSAGE_TEXT_LIMIT
    assert trimmed.endswith("…")


def test_truncate_short_text_unchanged():
    text = "Короткое сообщение"
    assert truncate_max_message_text(text) == text


def test_throttle_max_api_spacing():
    async def _run():
        start = time.monotonic()
        await throttle_max_api()
        await throttle_max_api()
        return time.monotonic() - start

    import asyncio

    elapsed = asyncio.run(_run())
    min_interval = 1.0 / MAX_API_TARGET_RPS
    assert elapsed >= min_interval * 0.9
