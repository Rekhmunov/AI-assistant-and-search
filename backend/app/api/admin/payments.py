from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_permissions import require_permission
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.admin import SubscriptionOut

router = APIRouter(prefix="/payments", tags=["admin-payments"])


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, le=100),
    _admin=Depends(require_permission("payments:read")),
):
    result = await db.execute(
        select(Subscription, User)
        .join(User, User.id == Subscription.user_id)
        .order_by(Subscription.created_at.desc())
        .limit(limit)
    )
    rows = result.all()
    out: list[SubscriptionOut] = []
    for sub, user in rows:
        hint = user.username or f"max:{user.max_user_id}"
        out.append(
            SubscriptionOut(
                id=sub.id,
                user_id=sub.user_id,
                yookassa_payment_id=sub.yookassa_payment_id,
                status=sub.status.value,
                amount_rub=sub.amount_rub,
                created_at=sub.created_at,
                activated_at=sub.activated_at,
                user_email_hint=hint,
            )
        )
    return out
