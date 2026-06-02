"""Rate limits and helpers for authentication endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

import redis.asyncio as redis

AUTH_WINDOW_SEC = 900
AUTH_MAX_ATTEMPTS = 15


def client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def check_auth_rate_limit(redis_client: redis.Redis, scope: str, identifier: str) -> None:
    key = f"auth_attempts:{scope}:{identifier.lower()}"
    attempts = await redis_client.incr(key)
    if attempts == 1:
        await redis_client.expire(key, AUTH_WINDOW_SEC)
    if attempts > AUTH_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток. Попробуйте позже.",
        )


async def clear_auth_rate_limit(redis_client: redis.Redis, scope: str, identifier: str) -> None:
    await redis_client.delete(f"auth_attempts:{scope}:{identifier.lower()}")
