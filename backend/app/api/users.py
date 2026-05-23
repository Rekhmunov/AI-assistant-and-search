from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_rate_limiter
from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.user import Plan, User
from app.schemas.user import UserProfile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfile)
async def get_me(
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    settings = get_settings()
    used = await limiter.get_search_usage(str(user.id))
    limit = settings.pro_searches_per_day if user.plan == Plan.PRO else settings.free_searches_per_day
    return UserProfile(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        language=user.language,
        plan=user.plan,
        plan_expires_at=user.plan_expires_at,
        searches_today=used,
        searches_limit=limit,
    )


@router.delete("/me")
async def delete_account(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    user.deleted_at = datetime.now(timezone.utc)
    return {"ok": True}
