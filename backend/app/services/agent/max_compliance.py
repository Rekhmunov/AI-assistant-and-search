"""Ограничения активности агентов в MAX — снижение риска бана и 429.

См. https://dev.max.ru/docs-api (30 rps, правила платформы).
"""

from __future__ import annotations

import asyncio
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

# Минимальный интервал между удалениями модератором в одном чате.
MODERATION_DELETE_COOLDOWN_SEC = 3.0
# Не чаще одного DM-ответа на команду от пользователя.
DM_COMMAND_COOLDOWN_SEC = 2.0
# Пауза между массовой рассылкой напоминаний одному боту.
DISPATCH_STAGGER_SEC = 0.15

_redis_client: Any = None


async def _redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_client


async def moderation_delete_allowed(chat_id: int) -> bool:
    """Не удалять сообщения пачкой — лимит MAX и жалобы пользователей."""
    key = f"max:mod:cd:{chat_id}"
    r = await _redis()
    if await r.set(key, "1", nx=True, ex=int(MODERATION_DELETE_COOLDOWN_SEC)):
        return True
    return False


async def dm_command_allowed(max_user_id: int) -> bool:
    key = f"max:dm:cd:{max_user_id}"
    r = await _redis()
    if await r.set(key, "1", nx=True, ex=int(DM_COMMAND_COOLDOWN_SEC)):
        return True
    return False


async def dispatch_stagger(index: int) -> None:
    """Пауза между отправками в одном цикле dispatch (снижает риск 429)."""
    if index > 0:
        await asyncio.sleep(DISPATCH_STAGGER_SEC)
