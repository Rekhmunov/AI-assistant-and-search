from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_permissions import require_permission
from app.models.admin_user import AdminUser
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User
from app.schemas.admin import BulkDeleteSubscriptionsRequest, SubscriptionOut
from app.services.admin_audit import log_admin_action
from app.services.admin_labels import (
    SUBSCRIPTION_STATUS_LABELS,
    format_admin_user_contacts,
    format_admin_user_label,
    subscription_status_label,
)

router = APIRouter(prefix="/payments", tags=["admin-payments"])


def _subscription_search_filters(term: str):
    cleaned = term.strip()
    if not cleaned:
        return None

    pattern = f"%{cleaned}%"
    filters = [
        User.email.ilike(pattern),
        User.username.ilike(pattern),
        User.first_name.ilike(pattern),
        User.last_name.ilike(pattern),
        Subscription.yookassa_payment_id.ilike(pattern),
        cast(Subscription.amount_rub, String).ilike(pattern),
        cast(Subscription.user_id, String).ilike(pattern),
        cast(Subscription.id, String).ilike(pattern),
        cast(Subscription.created_at, String).ilike(pattern),
        cast(Subscription.activated_at, String).ilike(pattern),
    ]

    if cleaned.isdigit():
        filters.append(User.max_user_id == int(cleaned))

    lowered = cleaned.lower()
    for status_value, label in SUBSCRIPTION_STATUS_LABELS.items():
        if lowered in label.lower() or lowered == status_value:
            filters.append(Subscription.status == SubscriptionStatus(status_value))

    return or_(*filters)


def _subscription_out(sub: Subscription, user: User) -> SubscriptionOut:
    status_value = sub.status.value if hasattr(sub.status, "value") else str(sub.status)
    return SubscriptionOut(
        id=sub.id,
        user_id=sub.user_id,
        yookassa_payment_id=sub.yookassa_payment_id,
        status=status_value,
        status_label=subscription_status_label(status_value),
        amount_rub=sub.amount_rub,
        created_at=sub.created_at,
        activated_at=sub.activated_at,
        user_email_hint=format_admin_user_label(user),
        user_email=user.email,
        user_max_user_id=user.max_user_id,
        user_contact_label=format_admin_user_contacts(user),
    )


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None),
    limit: int = Query(default=100, le=200),
    _admin=Depends(require_permission("payments:read")),
):
    q = select(Subscription, User).join(User, User.id == Subscription.user_id)
    search_filter = _subscription_search_filters(search) if search else None
    if search_filter is not None:
        q = q.where(search_filter)
    q = q.order_by(Subscription.created_at.desc()).limit(limit)
    result = await db.execute(q)
    rows = result.all()
    return [_subscription_out(sub, user) for sub, user in rows]


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("payments:write"))],
):
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подписка не найдена")

    payment_id = sub.yookassa_payment_id
    user_id = sub.user_id
    await db.delete(sub)
    await log_admin_action(
        db,
        admin=admin,
        action="subscription.delete",
        resource_type="subscription",
        resource_id=str(subscription_id),
        details={"user_id": str(user_id), "yookassa_payment_id": payment_id},
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True, "deleted": 1}


@router.post("/subscriptions/bulk-delete")
async def bulk_delete_subscriptions(
    body: BulkDeleteSubscriptionsRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("payments:write"))],
):
    result = await db.execute(select(Subscription).where(Subscription.id.in_(body.ids)))
    subs = list(result.scalars().all())
    if not subs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Выбранные подписки не найдены")

    for sub in subs:
        await db.delete(sub)

    await log_admin_action(
        db,
        admin=admin,
        action="subscription.bulk_delete",
        resource_type="subscription",
        resource_id=str(body.ids[0]),
        details={
            "count": len(subs),
            "ids": [str(sub.id) for sub in subs],
        },
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True, "deleted": len(subs)}
