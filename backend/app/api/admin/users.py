import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_rate_limiter, get_redis
from app.core.admin_permissions import require_permission
from app.core.config import get_settings
from app.models.admin_user import AdminUser
from app.models.message import Message, MessageRole
from app.models.thread import Thread
from app.models.user import Plan, User
from app.schemas.admin import (
    AdminMessageDebugOut,
    AdminSearchTurnOut,
    AdminThreadDebugOut,
    AdminThreadListItem,
    GrantProRequest,
    UserAdminOut,
    UserAdminUpdate,
)
from app.core.security import hash_password
from app.services.admin_audit import log_admin_action
from app.services.refresh_tokens import revoke_refresh_tokens
from app.services.subscription_activation import recover_pro_for_user, revoke_pro_for_user

router = APIRouter(prefix="/users", tags=["admin-users"])
logger = logging.getLogger(__name__)

MESSAGE_CONTENT_MAX = 12_000


def _plan_str(user: User) -> str:
    plan = user.plan
    if plan is None:
        return Plan.FREE.value
    if isinstance(plan, Plan):
        return plan.value
    return str(plan).lower()


def _clip(text: str, limit: int = MESSAGE_CONTENT_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


async def _threads_count(db: AsyncSession, user_id: UUID) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Thread)
            .where(Thread.user_id == user_id, Thread.deleted_at.is_(None))
        )
        or 0
    )


async def _user_out(
    db: AsyncSession,
    user: User,
    limiter,
    *,
    include_threads_count: bool = False,
) -> UserAdminOut:
    used = await limiter.get_search_usage(str(user.id))
    try:
        _, limit = await limiter.usage_and_limit(user)
    except Exception:
        logger.warning("Failed to resolve search limit for user %s", user.id, exc_info=True)
        limit = 0
    is_guest = bool(user.guest_key) and not user.email and user.max_user_id is None
    threads_count = await _threads_count(db, user.id) if include_threads_count else 0
    return UserAdminOut(
        id=user.id,
        max_user_id=user.max_user_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        plan=_plan_str(user),
        plan_expires_at=user.plan_expires_at,
        created_at=user.created_at,
        deleted_at=user.deleted_at,
        searches_today=used,
        searches_limit=limit,
        threads_count=threads_count,
        is_guest=is_guest,
    )


def _registered_user_filter():
    return or_(User.email.isnot(None), User.max_user_id.isnot(None))


def _message_debug_out(m: Message) -> AdminMessageDebugOut:
    role = m.role.value if hasattr(m.role, "value") else str(m.role)
    return AdminMessageDebugOut(
        id=m.id,
        role=role,
        content=_clip(m.content or ""),
        created_at=m.created_at,
        sources=m.sources if isinstance(m.sources, list) else None,
        follow_up_questions=m.follow_up_questions,
        debug_trace=m.debug_trace if isinstance(m.debug_trace, dict) else None,
    )


def _messages_to_turns(messages: list[Message]) -> list[AdminSearchTurnOut]:
    sorted_msgs = sorted(messages, key=lambda m: m.created_at)
    turns: list[AdminSearchTurnOut] = []
    pending_user: Message | None = None

    for m in sorted_msgs:
        role_val = m.role.value if hasattr(m.role, "value") else str(m.role)
        if role_val == MessageRole.USER.value:
            pending_user = m
        elif role_val == MessageRole.ASSISTANT.value and pending_user:
            turns.append(
                AdminSearchTurnOut(
                    user_message=_message_debug_out(pending_user),
                    assistant_message=_message_debug_out(m),
                )
            )
            pending_user = None

    if pending_user:
        turns.append(
            AdminSearchTurnOut(
                user_message=_message_debug_out(pending_user),
                assistant_message=None,
            )
        )
    return turns


@router.get("", response_model=list[UserAdminOut])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter=Depends(get_rate_limiter),
    search: str | None = Query(default=None),
    include_banned: bool = Query(default=False),
    include_guests: bool = Query(default=False),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(require_permission("users:read")),
):
    q = select(User)
    if not include_banned:
        q = q.where(User.deleted_at.is_(None))
    if not include_guests:
        q = q.where(_registered_user_filter())
    if search:
        term = f"%{search.strip()}%"
        filters = [
            User.username.ilike(term),
            User.email.ilike(term),
            User.first_name.ilike(term),
            User.guest_key.ilike(term),
        ]
        if search.strip().isdigit():
            filters.append(User.max_user_id == int(search.strip()))
        q = q.where(or_(*filters))

    q = q.order_by(User.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    users = result.scalars().all()
    out: list[UserAdminOut] = []
    for user in users:
        try:
            out.append(await _user_out(db, user, limiter))
        except Exception:
            logger.exception("Failed to serialize user %s for admin list", user.id)
    logger.info("Admin users list: returned %s of %s rows", len(out), len(users))
    return out


@router.get("/{user_id}", response_model=UserAdminOut)
async def get_user(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter=Depends(get_rate_limiter),
    _admin=Depends(require_permission("users:read")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await _user_out(db, user, limiter, include_threads_count=True)


@router.patch("/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: UUID,
    body: UserAdminUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("users:write"))],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    limiter=Depends(get_rate_limiter),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    changes: dict = {}
    if body.banned is not None:
        if body.banned:
            user.deleted_at = datetime.now(timezone.utc)
            changes["banned"] = True
        else:
            user.deleted_at = None
            changes["banned"] = False
    if body.plan is not None:
        user.plan = Plan(body.plan.lower())
        changes["plan"] = body.plan
    if body.plan_expires_at is not None:
        user.plan_expires_at = body.plan_expires_at
        changes["plan_expires_at"] = body.plan_expires_at.isoformat()
    if body.password is not None:
        if not user.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="У пользователя нет email — пароль задать нельзя",
            )
        user.password_hash = hash_password(body.password)
        changes["password"] = "changed"
        await revoke_refresh_tokens(redis_client, str(user.id))

    await log_admin_action(
        db,
        admin=admin,
        action="user.update",
        resource_type="user",
        resource_id=str(user_id),
        details=changes,
        ip_address=request.client.host if request.client else None,
    )
    return await _user_out(db, user, limiter, include_threads_count=True)


@router.get("/{user_id}/threads", response_model=list[AdminThreadListItem])
async def user_threads(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_deleted: bool = Query(default=True),
    limit: int = Query(default=50, le=100),
    _admin=Depends(require_permission("users:read")),
):
    q = select(Thread).where(Thread.user_id == user_id)
    if not include_deleted:
        q = q.where(Thread.deleted_at.is_(None))
    q = q.order_by(Thread.last_message_at.desc()).limit(limit)
    result = await db.execute(q)
    threads = result.scalars().all()
    return [
        AdminThreadListItem(
            id=t.id,
            title=t.title,
            message_count=t.message_count,
            last_message_at=t.last_message_at,
            created_at=t.created_at,
            deleted_at=t.deleted_at,
            deleted_by_user=t.deleted_at is not None,
        )
        for t in threads
    ]


@router.get("/{user_id}/threads/{thread_id}/debug", response_model=AdminThreadDebugOut)
async def user_thread_debug(
    user_id: UUID,
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("users:read")),
):
    result = await db.execute(
        select(Thread)
        .where(Thread.id == thread_id, Thread.user_id == user_id)
        .options(selectinload(Thread.messages))
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    return AdminThreadDebugOut(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at,
        last_message_at=thread.last_message_at,
        deleted_at=thread.deleted_at,
        deleted_by_user=thread.deleted_at is not None,
        turns=_messages_to_turns(list(thread.messages)),
    )


@router.post("/{user_id}/sync-pro-payment")
async def sync_pro_payment(
    user_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("payments:write"))],
):
    """Восстановить Pro по успешному платежу в ЮKassa (ручная синхронизация)."""
    settings = get_settings()
    if not settings.yookassa_shop_id.strip() or not settings.yookassa_secret_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="YooKassa не настроена")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    recovery = await recover_pro_for_user(db, user, settings=settings)
    await log_admin_action(
        db,
        admin=admin,
        action="user.sync_pro_payment",
        resource_type="user",
        resource_id=str(user_id),
        details={"ok": recovery.get("ok"), "source": recovery.get("source"), "payment_id": recovery.get("payment_id")},
        ip_address=request.client.host if request.client else None,
    )
    if recovery.get("ok"):
        await db.refresh(user)
    return recovery


@router.post("/{user_id}/grant-pro")
async def grant_pro(
    user_id: UUID,
    body: GrantProRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("payments:write"))],
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.plan = Plan.PRO
    user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=body.days)
    await log_admin_action(
        db,
        admin=admin,
        action="user.grant_pro",
        resource_type="user",
        resource_id=str(user_id),
        details={"days": body.days},
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True, "plan": "pro", "expires_at": user.plan_expires_at.isoformat()}


@router.post("/{user_id}/revoke-pro")
async def revoke_pro(
    user_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("payments:write"))],
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.plan != Plan.PRO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У пользователя нет активного тарифа Pro",
        )

    payload = await revoke_pro_for_user(db, user)
    await log_admin_action(
        db,
        admin=admin,
        action="user.revoke_pro",
        resource_type="user",
        resource_id=str(user_id),
        details={"canceled_subscriptions": payload["canceled_subscriptions"]},
        ip_address=request.client.host if request.client else None,
    )
    return payload
