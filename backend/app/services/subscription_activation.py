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
from app.services.yookassa import YooKassaError, get_payment, list_payments

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


async def find_pending_subscriptions(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[Subscription]:
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.PENDING,
        )
        .order_by(Subscription.created_at.desc())
    )
    return list(result.scalars().all())


async def find_latest_pending_subscription(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Subscription | None:
    pending = await find_pending_subscriptions(db, user_id)
    return pending[0] if pending else None


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


async def _try_activate_payment(
    db: AsyncSession,
    user: User,
    payment_id: str,
    payment_object: dict[str, Any],
    *,
    settings: Settings,
    source: str,
) -> dict[str, Any] | None:
    if await activate_from_yookassa_payment(
        db,
        payment_id=payment_id,
        payment_object=payment_object,
        settings=settings,
    ):
        await db.refresh(user)
        return {
            "ok": True,
            "plan": user.plan.value,
            "payment_id": payment_id,
            "source": source,
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        }
    return None


async def recover_pro_for_user(
    db: AsyncSession,
    user: User,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Restore Pro after YooKassa payment:
    1) check all pending subscriptions in DB
    2) scan recent succeeded payments in YooKassa by metadata.user_id
    """
    settings = settings or get_settings()
    if user.plan == Plan.PRO:
        return {"ok": True, "plan": "pro", "already_active": True}

    user_id_str = str(user.id)
    pending = await find_pending_subscriptions(db, user.id)

    for sub in pending:
        payment_id = (sub.yookassa_payment_id or "").strip()
        if not payment_id or payment_id.startswith("stub-"):
            continue
        try:
            payment = await get_payment(payment_id, settings)
        except YooKassaError:
            logger.warning("Could not fetch YooKassa payment %s for user %s", payment_id, user.id)
            continue
        if payment.get("status") != "succeeded":
            continue
        activated = await _try_activate_payment(
            db, user, payment_id, payment, settings=settings, source="pending_subscription"
        )
        if activated:
            return activated

    try:
        created_gte = datetime.now(timezone.utc) - timedelta(days=90)
        items = await list_payments(created_gte=created_gte, limit=100, settings=settings)
    except YooKassaError as e:
        logger.exception("YooKassa list payments failed for user %s", user.id)
        return {
            "ok": False,
            "message": f"Не удалось проверить платежи в ЮKassa: {e}",
        }

    for payment in items:
        if payment.get("status") != "succeeded":
            continue
        metadata = payment.get("metadata") or {}
        if str(metadata.get("user_id")) != user_id_str:
            continue
        payment_id = str(payment.get("id") or "")
        if not payment_id:
            continue
        activated = await _try_activate_payment(
            db, user, payment_id, payment, settings=settings, source="yookassa_scan"
        )
        if activated:
            logger.info("Recovered Pro for user %s via YooKassa scan, payment %s", user.id, payment_id)
            return activated

    if pending:
        latest_id = (pending[0].yookassa_payment_id or "").strip()
        if latest_id and not latest_id.startswith("stub-"):
            try:
                latest_payment = await get_payment(latest_id, settings)
                latest_status = latest_payment.get("status")
                if latest_status in ("pending", "waiting_for_capture"):
                    return {
                        "ok": False,
                        "status": latest_status,
                        "message": "Оплата ещё обрабатывается. Подождите 1–2 минуты и нажмите «Проверить оплату».",
                    }
            except YooKassaError:
                pass

    return {
        "ok": False,
        "message": (
            "Успешная оплата не найдена. Если деньги списались — напишите в поддержку "
            f"с email {user.email or 'аккаунта'}."
        ),
    }
