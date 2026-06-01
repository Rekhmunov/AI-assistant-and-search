"""Активация Pro после успешной оплаты YooKassa."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import Plan, User
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


async def activate_pro_for_user(
    db: AsyncSession,
    user: User,
    *,
    settings: Settings | None = None,
    notify_max: bool = True,
) -> None:
    settings = settings or get_settings()
    user.plan = Plan.PRO
    user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.pro_duration_days)
    if notify_max and user.max_user_id:
        bot = MaxBotService()
        await bot.send_message(user.max_user_id, "Подписка Pro активирована 🎉")


async def activate_subscription_record(
    db: AsyncSession,
    sub: Subscription,
    user: User,
    *,
    settings: Settings | None = None,
) -> bool:
    """Mark subscription active and upgrade user. Returns False if already active."""
    if sub.status == SubscriptionStatus.ACTIVE:
        return False
    sub.status = SubscriptionStatus.ACTIVE
    sub.activated_at = datetime.now(timezone.utc)
    await activate_pro_for_user(db, user, settings=settings)
    return True


async def find_subscription_by_payment_id(
    db: AsyncSession,
    payment_id: str,
) -> Subscription | None:
    result = await db.execute(
        select(Subscription).where(Subscription.yookassa_payment_id == payment_id)
    )
    return result.scalar_one_or_none()


async def find_latest_pending_subscription(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Subscription | None:
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.PENDING,
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def activate_from_yookassa_payment(
    db: AsyncSession,
    *,
    payment_id: str,
    payment_object: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> bool:
    """
    Activate Pro from YooKassa payment id.
    Returns True if user was upgraded (or already Pro on this payment).
    """
    settings = settings or get_settings()
    payment_object = payment_object or {}

    if payment_object.get("status") and payment_object.get("status") != "succeeded":
        logger.info("YooKassa payment %s status=%s — skip activation", payment_id, payment_object.get("status"))
        return False

    sub = await find_subscription_by_payment_id(db, payment_id)
    if sub is None:
        metadata = payment_object.get("metadata") or {}
        user_id_raw = metadata.get("user_id")
        amount_raw = (payment_object.get("amount") or {}).get("value")
        amount_rub = int(float(amount_raw)) if amount_raw else settings.pro_price_rub
        if user_id_raw:
            try:
                user_id = uuid.UUID(str(user_id_raw))
            except ValueError:
                user_id = None
            if user_id is not None:
                logger.warning(
                    "Subscription missing for payment %s — creating from metadata user_id=%s",
                    payment_id,
                    user_id,
                )
                sub = Subscription(
                    user_id=user_id,
                    yookassa_payment_id=payment_id,
                    status=SubscriptionStatus.PENDING,
                    amount_rub=amount_rub,
                )
                db.add(sub)
                await db.flush()

    if sub is None:
        logger.error("YooKassa payment %s succeeded but subscription not found and no metadata", payment_id)
        return False

    user_result = await db.execute(select(User).where(User.id == sub.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        logger.error("YooKassa payment %s — user %s not found", payment_id, sub.user_id)
        return False

    if user.plan == Plan.PRO and sub.status == SubscriptionStatus.ACTIVE:
        return True

    return await activate_subscription_record(db, sub, user, settings=settings)
