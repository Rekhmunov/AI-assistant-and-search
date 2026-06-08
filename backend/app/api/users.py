from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import clear_guest_cookie, clear_refresh_cookie, get_current_user, get_db, get_rate_limiter, get_redis
from app.core.request_security import verify_allowed_origin
from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.user import User
from app.schemas.user import UserProfile
from app.services.app_settings import get_setting
from app.services.refresh_tokens import revoke_refresh_tokens

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
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    user: Annotated[User, Depends(get_current_user)],
):
    verify_allowed_origin(request)
    user.deleted_at = datetime.now(timezone.utc)
    user.max_user_id = None
    await revoke_refresh_tokens(redis_client, str(user.id))
    clear_refresh_cookie(response)
    clear_guest_cookie(response)
    await db.commit()
    return {"ok": True}
