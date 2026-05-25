import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_rate_limiter
from app.core.admin_permissions import require_permission
from app.core.config import get_settings
from app.models.admin_user import AdminUser
from app.models.thread import Thread
from app.models.user import Plan, User
from app.schemas.admin import GrantProRequest, UserAdminOut, UserAdminUpdate
from app.schemas.thread import ThreadListItem
from app.services.admin_audit import log_admin_action

router = APIRouter(prefix="/users", tags=["admin-users"])
logger = logging.getLogger(__name__)


def _plan_str(user: User) -> str:
    plan = user.plan
    if plan is None:
        return Plan.FREE.value
    if isinstance(plan, Plan):
        return plan.value
    return str(plan).lower()


def _user_out(user: User, searches_today: int = 0) -> UserAdminOut:
    is_guest = bool(user.guest_key) and not user.email
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
        searches_today=searches_today,
        is_guest=is_guest,
    )


@router.get("", response_model=list[UserAdminOut])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter=Depends(get_rate_limiter),
    search: str | None = Query(default=None),
    include_banned: bool = Query(default=False),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(require_permission("users:read")),
):
    q = select(User)
    if not include_banned:
        q = q.where(User.deleted_at.is_(None))
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
            used = await limiter.get_search_usage(str(user.id))
        except Exception:
            logger.warning("Redis usage lookup failed for user %s", user.id, exc_info=True)
            used = 0
        try:
            out.append(_user_out(user, used))
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
    used = await limiter.get_search_usage(str(user.id))
    return _user_out(user, used)


@router.patch("/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: UUID,
    body: UserAdminUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("users:write"))],
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

    await log_admin_action(
        db,
        admin=admin,
        action="user.update",
        resource_type="user",
        resource_id=str(user_id),
        details=changes,
        ip_address=request.client.host if request.client else None,
    )
    used = await limiter.get_search_usage(str(user.id))
    return _user_out(user, used)


@router.get("/{user_id}/threads", response_model=list[ThreadListItem])
async def user_threads(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("users:read")),
):
    result = await db.execute(
        select(Thread).where(Thread.user_id == user_id).order_by(Thread.last_message_at.desc()).limit(20)
    )
    return result.scalars().all()


@router.post("/{user_id}/grant-pro")
async def grant_pro(
    user_id: UUID,
    body: GrantProRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("payments:write"))],
):
    settings = get_settings()
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
