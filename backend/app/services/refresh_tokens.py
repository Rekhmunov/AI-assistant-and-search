"""Refresh token generation counter (logout invalidates old refresh tokens)."""

from __future__ import annotations

import redis.asyncio as redis

_REFRESH_GEN_PREFIX = "user_refresh_gen:"


def _gen_key(user_id: str) -> str:
    return f"{_REFRESH_GEN_PREFIX}{user_id}"


async def get_refresh_generation(redis_client: redis.Redis, user_id: str) -> int:
    raw = await redis_client.get(_gen_key(user_id))
    if raw is None:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


async def revoke_refresh_tokens(redis_client: redis.Redis, user_id: str) -> int:
    return int(await redis_client.incr(_gen_key(user_id)))


def refresh_generation_matches(payload: dict, current_gen: int) -> bool:
    token_gen = payload.get("gen")
    if token_gen is None:
        return current_gen == 0
    try:
        return int(token_gen) == current_gen
    except (TypeError, ValueError):
        return False
