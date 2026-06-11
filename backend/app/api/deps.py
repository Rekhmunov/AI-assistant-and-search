import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

import redis.asyncio as redis
from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.auth_limits import client_ip
from app.core.limiter import RateLimiter
from app.core.security import decode_token
from app.services.refresh_tokens import get_refresh_generation, refresh_generation_matches
from app.models.admin_user import AdminUser
from app.models.user import Plan, User

security = HTTPBearer(auto_error=False)

GUEST_COOKIE = "guest_session"
GUEST_HEADER = "X-Guest-Session"

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def get_rate_limiter(r: Annotated[redis.Redis, Depends(get_redis)]) -> RateLimiter:
    return RateLimiter(r)


def set_guest_cookie(response: Response, guest_key: str) -> None:
    settings = get_settings()
    kwargs: dict = {
        "key": GUEST_COOKIE,
        "value": guest_key,
        "httponly": True,
        "secure": not settings.debug,
        "samesite": "none" if not settings.debug else "lax",
        "max_age": 60 * 60 * 24 * 365,
        "path": "/",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    response.set_cookie(**kwargs)


def set_admin_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    kwargs: dict = {
        "key": "admin_token",
        "value": token,
        "httponly": True,
        "secure": not settings.debug,
        "samesite": "none" if not settings.debug else "lax",
        "max_age": settings.admin_session_expire_hours * 3600,
        "path": "/",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    response.set_cookie(**kwargs)


def clear_admin_cookie(response: Response) -> None:
    settings = get_settings()
    kwargs: dict = {
        "key": "admin_token",
        "path": "/",
        "httponly": True,
        "secure": not settings.debug,
        "samesite": "none" if not settings.debug else "lax",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    response.delete_cookie(**kwargs)


def clear_guest_cookie(response: Response) -> None:
    settings = get_settings()
    kwargs: dict = {
        "key": GUEST_COOKIE,
        "path": "/",
        "httponly": True,
        "secure": not settings.debug,
        "samesite": "none" if not settings.debug else "lax",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    response.delete_cookie(**kwargs)


def clear_refresh_cookie(response: Response, request: Request | None = None) -> None:
    from app.core.auth_cookies import refresh_cookie_delete_kwargs

    response.delete_cookie(**refresh_cookie_delete_kwargs(request=request))


async def _user_from_access_token(db: AsyncSession, token: str) -> User | None:
    settings = get_settings()
    payload = decode_token(token, "access", settings)
    if not payload or not payload.get("sub"):
        return None
    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def _user_from_refresh_cookie(
    db: AsyncSession,
    refresh_token: str | None,
    redis_client: redis.Redis | None = None,
) -> User | None:
    if not refresh_token:
        return None
    settings = get_settings()
    payload = decode_token(refresh_token, "refresh", settings)
    if not payload or not payload.get("sub"):
        return None
    user_id = uuid.UUID(payload["sub"])
    if redis_client is not None:
        current_gen = await get_refresh_generation(redis_client, str(user_id))
        if not refresh_generation_matches(payload, current_gen):
            return None
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def require_admin_or_api_key(
    db: Annotated[AsyncSession, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    admin_token: Annotated[str | None, Cookie(alias="admin_token")] = None,
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    """Admin session cookie or X-Admin-Key for operational endpoints (e.g. LLM health probes)."""
    settings = get_settings()
    from app.core.secrets import secrets_match

    if settings.admin_api_key and x_admin_key and secrets_match(x_admin_key, settings.admin_api_key):
        return
    try:
        await get_current_admin(db, creds, admin_token)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized") from None


async def guest_by_key(db: AsyncSession, guest_key: str | None) -> User | None:
    if not guest_key:
        return None
    result = await db.execute(
        select(User).where(
            User.guest_key == guest_key,
            User.email.is_(None),
            User.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _resolve_authenticated_user(
    db: AsyncSession,
    creds: HTTPAuthorizationCredentials | None,
    refresh_token: str | None,
    redis_client: redis.Redis | None = None,
) -> User | None:
    if creds and creds.credentials:
        user = await _user_from_access_token(db, creds.credentials)
        if user:
            return user
    return await _user_from_refresh_cookie(db, refresh_token, redis_client)


@dataclass
class SearchUserResult:
    user: User
    new_guest_key: str | None = None


async def resolve_search_user(
    db: AsyncSession,
    creds: HTTPAuthorizationCredentials | None,
    refresh_token: str | None,
    guest_session: str | None,
    x_guest_session: str | None,
    *,
    create_guest: bool,
    request: Request | None = None,
    limiter: RateLimiter | None = None,
    redis_client: redis.Redis | None = None,
) -> SearchUserResult:
    """JWT user, existing guest, or (if create_guest) a new guest row."""
    user = await _resolve_authenticated_user(db, creds, refresh_token, redis_client)
    if user:
        return SearchUserResult(user=user)

    guest_key = (guest_session or x_guest_session or "").strip() or None
    guest = await guest_by_key(db, guest_key)
    if guest:
        return SearchUserResult(user=guest)

    if not create_guest:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")

    if limiter is not None and request is not None:
        await limiter.check_guest_creation_limit(client_ip(request))

    new_key = secrets.token_urlsafe(32)
    guest = User(guest_key=new_key, plan=Plan.FREE)
    db.add(guest)
    await db.flush()
    await db.commit()
    return SearchUserResult(user=guest, new_guest_key=new_key)


async def get_search_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    refresh_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
    x_guest_session: Annotated[str | None, Header(alias=GUEST_HEADER)] = None,
) -> SearchUserResult:
    return await resolve_search_user(
        db,
        creds,
        refresh_token,
        guest_session,
        x_guest_session,
        create_guest=True,
        request=request,
        limiter=limiter,
        redis_client=redis_client,
    )


async def get_existing_search_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    refresh_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
    x_guest_session: Annotated[str | None, Header(alias=GUEST_HEADER)] = None,
) -> SearchUserResult:
    return await resolve_search_user(
        db,
        creds,
        refresh_token,
        guest_session,
        x_guest_session,
        create_guest=False,
        request=request,
        redis_client=redis_client,
    )


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    refresh_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
) -> User:
    user = await _resolve_authenticated_user(db, creds, refresh_token, redis_client)
    if user:
        return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")


async def get_file_access_user(
    access: Annotated[SearchUserResult, Depends(get_existing_search_user)],
) -> User:
    """JWT, refresh cookie или гостевая сессия — для скачивания своих файлов."""
    return access.user


async def get_current_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    admin_token: Annotated[str | None, Cookie(alias="admin_token")] = None,
) -> AdminUser:
    settings = get_settings()
    token: str | None = None
    if creds and creds.credentials:
        token = creds.credentials
    elif admin_token:
        token = admin_token

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")

    payload = decode_token(token, "admin", settings)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен сессии")

    admin_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Администратор не найден")
    return admin


async def verify_admin_api_key(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    """Legacy header auth; prefer admin session cookie."""
    settings = get_settings()
    from app.core.secrets import secrets_match

    if not settings.admin_api_key or not secrets_match(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещён")
