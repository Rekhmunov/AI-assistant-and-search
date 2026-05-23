from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_rate_limiter
from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    init_data_is_fresh,
    parse_init_data_user,
    validate_max_init_data,
)
from app.models.user import Plan, User
from app.schemas.auth import AuthResponse, InitDataRequest, TokenResponse
from app.schemas.user import UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_profile(user: User, used: int, limit: int) -> UserProfile:
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


async def _limits_for_user(user: User, limiter: RateLimiter) -> tuple[int, int]:
    settings = get_settings()
    used = await limiter.get_search_usage(str(user.id))
    limit = settings.pro_searches_per_day if user.plan == Plan.PRO else settings.free_searches_per_day
    return used, limit


@router.post("/login", response_model=AuthResponse)
async def login(
    body: InitDataRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    settings = get_settings()
    init_data = body.init_data.strip()

    if not settings.skip_init_data_validation:
        if not settings.bot_token:
            raise HTTPException(status_code=500, detail="Bot token not configured")
        if not validate_max_init_data(init_data, settings.bot_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid initData")
        if not init_data_is_fresh(init_data, settings.init_data_max_age_seconds):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="initData expired")

    user_data = parse_init_data_user(init_data)
    if not user_data or "id" not in user_data:
        if settings.skip_init_data_validation:
            user_data = {"id": 1, "first_name": "Dev", "last_name": "User", "language_code": "ru"}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User data missing")

    max_user_id = int(user_data["id"])
    result = await db.execute(select(User).where(User.max_user_id == max_user_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            max_user_id=max_user_id,
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            username=user_data.get("username"),
            language=user_data.get("language_code", "ru"),
        )
        db.add(user)
        await db.flush()
    else:
        user.first_name = user_data.get("first_name") or user.first_name
        user.last_name = user_data.get("last_name") or user.last_name
        user.username = user_data.get("username") or user.username
        if user.plan == Plan.PRO and user.plan_expires_at and user.plan_expires_at < datetime.now(timezone.utc):
            user.plan = Plan.FREE
            user.plan_expires_at = None

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))

    response.set_cookie(
        key="refresh_token",
        value=refresh,
        httponly=True,
        secure=not settings.debug,
        samesite="none" if not settings.debug else "lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )

    used, limit = await _limits_for_user(user, limiter)
    return AuthResponse(access_token=access, user=_user_profile(user, used, limit))


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie()] = None,
):
    settings = get_settings()
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = decode_token(refresh_token, "refresh", settings)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access = create_access_token(str(user.id))
    new_refresh = create_refresh_token(str(user.id))
    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=not settings.debug,
        samesite="none" if not settings.debug else "lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )
    return TokenResponse(access_token=access)
