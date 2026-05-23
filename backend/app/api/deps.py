import uuid
from typing import Annotated

import redis.asyncio as redis
from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.limiter import RateLimiter
from app.core.security import decode_token
from app.models.user import User

security = HTTPBearer(auto_error=False)

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def get_rate_limiter(r: Annotated[redis.Redis, Depends(get_redis)]) -> RateLimiter:
    return RateLimiter(r)


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    refresh_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
) -> User:
    settings = get_settings()
    token: str | None = None
    if creds and creds.credentials:
        token = creds.credentials
    elif refresh_token:
        payload = decode_token(refresh_token, "refresh", settings)
        if payload and payload.get("sub"):
            token = None
            user_id = uuid.UUID(payload["sub"])
            result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
            user = result.scalar_one_or_none()
            if user:
                return user

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(token, "access", settings)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def verify_admin_api_key(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    settings = get_settings()
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
