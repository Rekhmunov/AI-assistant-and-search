from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    GUEST_COOKIE,
    GUEST_HEADER,
    clear_guest_cookie,
    get_current_user,
    get_db,
    get_rate_limiter,
    guest_by_key,
)
from app.core.config import get_settings

_session_security = HTTPBearer(auto_error=False)
from app.core.limiter import RateLimiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    init_data_is_fresh,
    parse_init_data_user,
    validate_max_init_data,
    verify_password,
)
from app.models.user import Plan, User
from app.models.thread import Thread
from app.schemas.auth import (
    AuthResponse,
    EmailLoginRequest,
    EmailRegisterRequest,
    InitDataRequest,
    SessionStatus,
    TokenResponse,
)
from app.schemas.user import UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, user_id: str) -> tuple[str, str]:
    settings = get_settings()
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    response.set_cookie(
        key="refresh_token",
        value=refresh,
        httponly=True,
        secure=not settings.debug,
        samesite="none" if not settings.debug else "lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )
    return access, refresh


def _user_profile(user: User, used: int, limit: int) -> UserProfile:
    return UserProfile(
        id=user.id,
        email=user.email,
        max_linked=user.max_user_id is not None,
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
    return await limiter.usage_and_limit(user)


async def _merge_guest_session(
    db: AsyncSession,
    guest_key: str | None,
    user: User,
) -> None:
    if not guest_key or user.guest_key == guest_key:
        return
    result = await db.execute(
        select(User).where(
            User.guest_key == guest_key,
            User.email.is_(None),
            User.id != user.id,
            User.deleted_at.is_(None),
        )
    )
    guest = result.scalar_one_or_none()
    if not guest:
        return
    await db.execute(update(Thread).where(Thread.user_id == guest.id).values(user_id=user.id))
    await db.delete(guest)


@router.get("/session", response_model=SessionStatus)
async def session_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_session_security)],
    refresh_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
    x_guest_session: Annotated[str | None, Header(alias=GUEST_HEADER)] = None,
):
    from app.api.deps import _resolve_authenticated_user

    settings = get_settings()
    user = await _resolve_authenticated_user(db, creds, refresh_token)
    if user:
        used, limit = await _limits_for_user(user, limiter)
        return SessionStatus(
            authenticated=True,
            is_guest=False,
            searches_today=used,
            searches_limit=limit,
            user=_user_profile(user, used, limit),
        )

    guest_key = (guest_session or x_guest_session or "").strip() or None
    guest = await guest_by_key(db, guest_key)
    if guest:
        used, limit = await _limits_for_user(guest, limiter)
        return SessionStatus(
            authenticated=False,
            is_guest=True,
            searches_today=used,
            searches_limit=limit,
        )

    return SessionStatus(
        authenticated=False,
        is_guest=False,
        searches_today=0,
        searches_limit=settings.guest_searches_per_day,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    body: InitDataRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
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

    await _merge_guest_session(db, guest_session, user)
    clear_guest_cookie(response)
    access, _ = _set_auth_cookies(response, str(user.id))
    used, limit = await _limits_for_user(user, limiter)
    return AuthResponse(access_token=access, user=_user_profile(user, used, limit))


@router.post("/register", response_model=AuthResponse)
async def register_email(
    body: EmailRegisterRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
):
    email = body.email.strip().lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email уже зарегистрирован")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        first_name=body.first_name,
        max_user_id=None,
    )
    db.add(user)
    await db.flush()

    await _merge_guest_session(db, guest_session, user)
    clear_guest_cookie(response)
    access, _ = _set_auth_cookies(response, str(user.id))
    used, limit = await _limits_for_user(user, limiter)
    return AuthResponse(access_token=access, user=_user_profile(user, used, limit))


@router.post("/email-login", response_model=AuthResponse)
async def login_email(
    body: EmailLoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
):
    email = body.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")

    if user.plan == Plan.PRO and user.plan_expires_at and user.plan_expires_at < datetime.now(timezone.utc):
        user.plan = Plan.FREE
        user.plan_expires_at = None

    await _merge_guest_session(db, guest_session, user)
    clear_guest_cookie(response)
    access, _ = _set_auth_cookies(response, str(user.id))
    used, limit = await _limits_for_user(user, limiter)
    return AuthResponse(access_token=access, user=_user_profile(user, used, limit))


@router.post("/bind-max", response_model=UserProfile)
async def bind_max(
    body: InitDataRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    """Привязать MAX-аккаунт к текущему пользователю (после входа по email)."""
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User data missing")

    max_user_id = int(user_data["id"])
    other = await db.execute(select(User).where(User.max_user_id == max_user_id, User.id != user.id))
    if other.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Этот MAX уже привязан к другому аккаунту")

    user.max_user_id = max_user_id
    user.first_name = user_data.get("first_name") or user.first_name
    user.last_name = user_data.get("last_name") or user.last_name
    user.username = user_data.get("username") or user.username

    used, limit = await _limits_for_user(user, limiter)
    return _user_profile(user, used, limit)


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
