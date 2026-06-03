from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    GUEST_COOKIE,
    GUEST_HEADER,
    clear_guest_cookie,
    clear_refresh_cookie,
    get_current_user,
    get_db,
    get_rate_limiter,
    get_redis,
    guest_by_key,
)
from app.core.auth_limits import check_auth_rate_limit, clear_auth_rate_limit, client_ip
from app.core.config import get_settings
from app.core.request_security import verify_allowed_origin
from app.services.app_settings import get_setting
from app.services.refresh_tokens import get_refresh_generation, refresh_generation_matches, revoke_refresh_tokens

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
    BindMaxCompleteRequest,
    BindMaxStartResponse,
    EmailLoginRequest,
    ChangePasswordRequest,
    EmailRegisterRequest,
    InitDataRequest,
    SessionStatus,
    TokenResponse,
)
from app.schemas.user import UserProfile
from app.services.max_bind_token import BIND_TOKEN_TTL_SEC, consume_max_bind_token, create_max_bind_token

import redis.asyncio as redis

router = APIRouter(prefix="/auth", tags=["auth"])


async def _set_auth_cookies(
    response: Response,
    user_id: str,
    redis_client: redis.Redis,
) -> str:
    settings = get_settings()
    gen = await get_refresh_generation(redis_client, user_id)
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id, refresh_gen=gen)
    cookie_kwargs: dict = {
        "key": "refresh_token",
        "value": refresh,
        "httponly": True,
        "secure": not settings.debug,
        "samesite": "none" if not settings.debug else "lax",
        "max_age": settings.refresh_token_expire_days * 86400,
        "path": "/",
    }
    if settings.cookie_domain:
        cookie_kwargs["domain"] = settings.cookie_domain
    response.set_cookie(**cookie_kwargs)
    return access


def _user_profile(user: User, used: int, limit: int) -> UserProfile:
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


def _validate_init_data(init_data: str) -> dict:
    settings = get_settings()
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
            return {"id": 1, "first_name": "Dev", "last_name": "User", "language_code": "ru"}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User data missing")
    return user_data


async def _attach_max_identity(db: AsyncSession, user: User, user_data: dict) -> None:
    max_user_id = int(user_data["id"])
    other = await db.execute(select(User).where(User.max_user_id == max_user_id, User.id != user.id))
    if other.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Этот MAX уже привязан к другому аккаунту")

    user.max_user_id = max_user_id
    user.first_name = user_data.get("first_name") or user.first_name
    user.last_name = user_data.get("last_name") or user.last_name
    user.username = user_data.get("username") or user.username


@router.get("/session", response_model=SessionStatus)
async def session_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_session_security)],
    refresh_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
    x_guest_session: Annotated[str | None, Header(alias=GUEST_HEADER)] = None,
):
    from app.api.deps import _resolve_authenticated_user

    settings = get_settings()
    guest_limit = int(await get_setting("guest_searches_per_day", db, redis_client, settings))
    pro_price_rub = int(await get_setting("pro_price_rub", db, redis_client, settings))
    user = await _resolve_authenticated_user(db, creds, refresh_token, redis_client)
    if user:
        used, limit = await _limits_for_user(user, limiter)
        return SessionStatus(
            authenticated=True,
            is_guest=False,
            searches_today=used,
            searches_limit=limit,
            pro_price_rub=pro_price_rub,
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
            pro_price_rub=pro_price_rub,
        )

    return SessionStatus(
        authenticated=False,
        is_guest=False,
        searches_today=0,
        searches_limit=guest_limit,
        pro_price_rub=pro_price_rub,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: Request,
    body: InitDataRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
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
        if user.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Вы попали в бан, обратитесь в поддержку",
            )
        user.first_name = user_data.get("first_name") or user.first_name
        user.last_name = user_data.get("last_name") or user.last_name
        user.username = user_data.get("username") or user.username
        if user.plan == Plan.PRO and user.plan_expires_at and user.plan_expires_at < datetime.now(timezone.utc):
            user.plan = Plan.FREE
            user.plan_expires_at = None

    await _merge_guest_session(db, guest_session, user)
    clear_guest_cookie(response)
    access = await _set_auth_cookies(response, str(user.id), redis_client)
    used, limit = await _limits_for_user(user, limiter)
    return AuthResponse(access_token=access, user=_user_profile(user, used, limit))


def _db_schema_error(exc: Exception) -> HTTPException | None:
    msg = str(exc).lower()
    if "email" in msg or "password_hash" in msg or "guest_key" in msg or "undefinedcolumn" in msg:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База не обновлена. Выполните: docker compose -f docker-compose.prod.yml exec backend alembic upgrade head",
        )
    return None


@router.post("/register", response_model=AuthResponse)
async def register_email(
    request: Request,
    body: EmailRegisterRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
):
    verify_allowed_origin(request)
    email = body.email.strip().lower()
    ip = client_ip(request)
    await check_auth_rate_limit(redis_client, "register", ip)
    await check_auth_rate_limit(redis_client, "register_email", email)
    try:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не удалось завершить регистрацию. Проверьте данные или войдите в аккаунт.",
            )

        user = User(
            email=email,
            password_hash=hash_password(body.password),
            first_name=body.first_name,
            max_user_id=None,
        )
        db.add(user)
        try:
            await db.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не удалось завершить регистрацию. Проверьте данные или войдите в аккаунт.",
            ) from exc

        await clear_auth_rate_limit(redis_client, "register", ip)
        await clear_auth_rate_limit(redis_client, "register_email", email)
        await _merge_guest_session(db, guest_session, user)
        clear_guest_cookie(response)
        access = await _set_auth_cookies(response, str(user.id), redis_client)
        used, limit = await _limits_for_user(user, limiter)
        return AuthResponse(access_token=access, user=_user_profile(user, used, limit))
    except HTTPException:
        raise
    except ProgrammingError as exc:
        raise _db_schema_error(exc) or HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ошибка базы данных при регистрации",
        ) from exc
    except Exception as exc:
        schema_err = _db_schema_error(exc)
        if schema_err:
            raise schema_err from exc
        import logging

        logging.getLogger(__name__).exception("register_email failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось зарегистрироваться. Попробуйте позже.",
        ) from exc


@router.post("/email-login", response_model=AuthResponse)
async def login_email(
    request: Request,
    body: EmailLoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
):
    verify_allowed_origin(request)
    email = body.email.strip().lower()
    ip = client_ip(request)
    await check_auth_rate_limit(redis_client, "login", ip)
    await check_auth_rate_limit(redis_client, "login_email", email)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы попали в бан, обратитесь в поддержку",
        )

    if user.plan == Plan.PRO and user.plan_expires_at and user.plan_expires_at < datetime.now(timezone.utc):
        user.plan = Plan.FREE
        user.plan_expires_at = None

    await clear_auth_rate_limit(redis_client, "login", ip)
    await clear_auth_rate_limit(redis_client, "login_email", email)
    await _merge_guest_session(db, guest_session, user)
    clear_guest_cookie(response)
    access = await _set_auth_cookies(response, str(user.id), redis_client)
    used, limit = await _limits_for_user(user, limiter)
    return AuthResponse(access_token=access, user=_user_profile(user, used, limit))


@router.post("/change-password", response_model=UserProfile)
async def change_password(
    body: ChangePasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
):
    """Смена пароля для входа по email."""
    if not user.email or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала привяжите email и пароль",
        )
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный текущий пароль")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Новый пароль должен отличаться от текущего",
        )
    user.password_hash = hash_password(body.new_password)
    await revoke_refresh_tokens(redis_client, str(user.id))
    used, limit = await _limits_for_user(user, limiter)
    return _user_profile(user, used, limit)


@router.post("/bind-email", response_model=UserProfile)
async def bind_email(
    body: EmailRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    """Добавить email и пароль к аккаунту MAX (вход с сайта glosix.ru)."""
    if user.email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email уже привязан")

    email = body.email.strip().lower()
    existing = await db.execute(
        select(User).where(User.email == email, User.id != user.id, User.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось привязать email. Проверьте данные или используйте другой адрес.",
        )

    user.email = email
    user.password_hash = hash_password(body.password)
    if body.first_name and not user.first_name:
        user.first_name = body.first_name

    used, limit = await _limits_for_user(user, limiter)
    return _user_profile(user, used, limit)


@router.post("/bind-max", response_model=UserProfile)
async def bind_max(
    body: InitDataRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    """Привязать MAX-аккаунт к текущему пользователю (миниапп, тот же WebView)."""
    if user.max_user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MAX уже привязан")

    user_data = _validate_init_data(body.init_data.strip())
    await _attach_max_identity(db, user, user_data)

    used, limit = await _limits_for_user(user, limiter)
    return _user_profile(user, used, limit)


@router.post("/bind-max/start", response_model=BindMaxStartResponse)
async def bind_max_start(
    user: Annotated[User, Depends(get_current_user)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
):
    """С сайта: одноразовый токен для deeplink startapp=bind_<token>."""
    if user.max_user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MAX уже привязан")

    bind_token = await create_max_bind_token(redis_client, user.id)
    return BindMaxStartResponse(bind_token=bind_token, expires_in=BIND_TOKEN_TTL_SEC)


@router.post("/bind-max/complete", response_model=AuthResponse)
async def bind_max_complete(
    body: BindMaxCompleteRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    guest_session: Annotated[str | None, Cookie(alias=GUEST_COOKIE)] = None,
):
    """Миниапп MAX: завершить привязку по токену из startapp и initData."""
    user_id = await consume_max_bind_token(redis_client, body.bind_token.strip())
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка для привязки устарела. Вернитесь на сайт и нажмите «Открыть в MAX» снова.",
        )

    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if user.max_user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MAX уже привязан")

    user_data = _validate_init_data(body.init_data.strip())
    await _attach_max_identity(db, user, user_data)

    await _merge_guest_session(db, guest_session, user)
    clear_guest_cookie(response)
    access = await _set_auth_cookies(response, str(user.id), redis_client)
    used, limit = await _limits_for_user(user, limiter)
    return AuthResponse(access_token=access, user=_user_profile(user, used, limit))


@router.post("/logout")
async def logout(
    response: Response,
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    refresh_token: Annotated[str | None, Cookie(alias="refresh_token")] = None,
):
    """Clear server session cookies so the client can continue as a guest."""
    settings = get_settings()
    if refresh_token:
        payload = decode_token(refresh_token, "refresh", settings)
        if payload and payload.get("sub"):
            await revoke_refresh_tokens(redis_client, str(payload["sub"]))
    clear_refresh_cookie(response)
    clear_guest_cookie(response)
    return {"ok": True}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    refresh_token: Annotated[str | None, Cookie()] = None,
):
    settings = get_settings()
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = decode_token(refresh_token, "refresh", settings)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = UUID(payload["sub"])
    current_gen = await get_refresh_generation(redis_client, str(user_id))
    if not refresh_generation_matches(payload, current_gen):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access = create_access_token(str(user.id))
    new_refresh = create_refresh_token(str(user.id), refresh_gen=current_gen)
    cookie_kwargs: dict = {
        "key": "refresh_token",
        "value": new_refresh,
        "httponly": True,
        "secure": not settings.debug,
        "samesite": "none" if not settings.debug else "lax",
        "max_age": settings.refresh_token_expire_days * 86400,
        "path": "/",
    }
    if settings.cookie_domain:
        cookie_kwargs["domain"] = settings.cookie_domain
    response.set_cookie(**cookie_kwargs)
    return TokenResponse(access_token=access)
