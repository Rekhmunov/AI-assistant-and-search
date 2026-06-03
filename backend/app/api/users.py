from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_rate_limiter, get_redis
from app.core.request_security import verify_allowed_origin
from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.user import User
from app.schemas.user import UserProfile
from app.services.app_settings import get_setting

import redis.asyncio as redis

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfile)
async def get_me(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    settings = get_settings()
    used, limit = await limiter.usage_and_limit(user)
    pro_price_rub = int(await get_setting("pro_price_rub", db, redis_client, settings))
    return UserProfile(
        id=user.id,
        email=user.email,
        max_linked=user.max_user_id is not None,
        max_user_id=user.max_user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        language=user.language,
        plan=user.plan,
        plan_expires_at=user.plan_expires_at,
        searches_today=used,
        searches_limit=limit,
        pro_price_rub=pro_price_rub,
    )


@router.delete("/me")
async def delete_account(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    verify_allowed_origin(request)
    user.deleted_at = datetime.now(timezone.utc)
    return {"ok": True}
