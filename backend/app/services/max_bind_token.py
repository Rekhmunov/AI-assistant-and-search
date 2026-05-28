"""Одноразовые токены привязки MAX с сайта (deeplink startapp=bind_…)."""

from __future__ import annotations

import secrets
from uuid import UUID

import redis.asyncio as redis

BIND_TOKEN_PREFIX = "max_bind:"
BIND_TOKEN_TTL_SEC = 900


async def create_max_bind_token(redis_client: redis.Redis, user_id: UUID) -> str:
    token = secrets.token_urlsafe(24)
    key = f"{BIND_TOKEN_PREFIX}{token}"
    await redis_client.setex(key, BIND_TOKEN_TTL_SEC, str(user_id))
    return token


async def consume_max_bind_token(redis_client: redis.Redis, token: str) -> UUID | None:
    raw = (token or "").strip()
    if not raw:
        return None
    key = f"{BIND_TOKEN_PREFIX}{raw}"
    user_id = await redis_client.get(key)
    if not user_id:
        return None
    await redis_client.delete(key)
    try:
        return UUID(str(user_id))
    except ValueError:
        return None
