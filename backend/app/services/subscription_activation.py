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
from app.services.yookassa import YooKassaError, get_payment, list_all_payments

logger = logging.getLogger(__name__)

PAYMENT_PROCESSING_STATUSES = frozenset({"pending", "waiting_for_capture"})
RECENT_PENDING_WINDOW = timedelta(hours=2)


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
    await db.flush()
    if notify_max and user.max_user_id:
        bot = MaxBotService()
        await bot.send_message(user.max_user_id, "Подписка Pro активирована 🎉")


async def _reload_user_plan(db: AsyncSession, user: User) -> None:
    await db.flush()
    await db.refresh(user, attribute_names=["plan", "plan_expires_at"])


async def _activation_success(
    db: AsyncSession,
    user: User,
    *,
    payment_id: str,
    source: str,
) -> dict[str, Any] | None:
    await _reload_user_plan(db, user)
    if user.plan != Plan.PRO:
        logger.error(
            "Pro activation reported success but user %s plan=%s (payment %s, source=%s)",
            user.id,
            user.plan,
            payment_id,
            source,
        )
        return None
    return {
        "ok": True,
        "plan": user.plan.value,
        "payment_id": payment_id,
        "source": source,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
    }


async def activate_subscription_record(
    db: AsyncSession,
    sub: Subscription,
    user: User,
    *,
    settings: Settings | None = None,
) -> bool:
    """Mark subscription active and upgrade user plan to Pro."""
    if sub.status != SubscriptionStatus.ACTIVE:
        sub.status = SubscriptionStatus.ACTIVE
        sub.activated_at = datetime.now(timezone.utc)

    if user.plan != Plan.PRO:
        await activate_pro_for_user(db, user, settings=settings)

    return user.plan == Plan.PRO


async def find_subscription_by_payment_id(
    db: AsyncSession,
    payment_id: str,
) -> Subscription | None:
    result = await db.execute(
        select(Subscription).where(Subscription.yookassa_payment_id == payment_id)
    )
    return result.scalar_one_or_none()


async def find_user_subscriptions(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[Subscription]:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_pro_for_user(db: AsyncSession, user: User) -> dict[str, Any]:
    """Downgrade user to Free and cancel active/pending subscriptions."""
    canceled = 0
    for sub in await find_user_subscriptions(db, user.id):
        if sub.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PENDING):
            sub.status = SubscriptionStatus.CANCELED
            canceled += 1

    user.plan = Plan.FREE
    user.plan_expires_at = None
    await db.flush()
    return {"ok": True, "plan": Plan.FREE.value, "canceled_subscriptions": canceled}


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


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def payment_amount_is_valid(payment_object: dict[str, Any], expected_rub: int) -> bool:
    amount_block = payment_object.get("amount") or {}
    value = amount_block.get("value")
    currency = str(amount_block.get("currency") or "RUB").upper()
    if value is None or currency != "RUB":
        return False
    try:
        paid = int(round(float(str(value))))
    except (TypeError, ValueError):
        return False
    return paid == int(expected_rub)


def _technical_receipt_email(user: User, settings: Settings | None = None) -> str | None:
    if user.max_user_id is None:
        return None
    settings = settings or get_settings()
    host = settings.public_web_url.replace("https://", "").replace("http://", "").split("/")[0]
    return f"max{user.max_user_id}@{host}".lower()


def payment_matches_user(
    payment: dict[str, Any],
    user: User,
    *,
    settings: Settings | None = None,
) -> bool:
    metadata = payment.get("metadata") or {}
    if str(metadata.get("user_id")) == str(user.id):
        return True

    receipt = payment.get("receipt") or {}
    customer = receipt.get("customer") or {}
    receipt_email = _normalize_email(str(customer.get("email") or ""))
    if not receipt_email:
        return False

    user_email = _normalize_email(user.email)
    if user_email and receipt_email == user_email:
        return True

    technical = _technical_receipt_email(user, settings)
    if technical and receipt_email == technical:
        return True

    return False


async def activate_from_yookassa_payment(
    db: AsyncSession,
    *,
    payment_id: str,
    payment_object: dict[str, Any] | None = None,
    settings: Settings | None = None,
    expected_user: User | None = None,
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

        user_id: uuid.UUID | None = None
        if user_id_raw:
            try:
                user_id = uuid.UUID(str(user_id_raw))
            except ValueError:
                user_id = None

        if user_id is None and expected_user is not None and payment_matches_user(payment_object, expected_user):
            user_id = expected_user.id

        if user_id is None:
            receipt = payment_object.get("receipt") or {}
            customer = receipt.get("customer") or {}
            receipt_email = _normalize_email(str(customer.get("email") or ""))
            if receipt_email:
                user_result = await db.execute(select(User).where(User.email.ilike(receipt_email)))
                matched_user = user_result.scalar_one_or_none()
                if matched_user is not None:
                    user_id = matched_user.id

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

    target_user = expected_user if expected_user is not None else user
    if target_user.id != user.id:
        logger.error(
            "Payment %s belongs to user %s, cannot activate for user %s",
            payment_id,
            user.id,
            target_user.id,
        )
        return False

    if target_user.plan == Plan.PRO and sub.status == SubscriptionStatus.ACTIVE:
        return True

    amount_value = (payment_object.get("amount") or {}).get("value")
    if amount_value is not None:
        expected_rub = int(sub.amount_rub or settings.pro_price_rub)
        if not payment_amount_is_valid(payment_object, expected_rub):
            logger.error(
                "YooKassa payment %s amount mismatch (expected %s RUB, got %s)",
                payment_id,
                expected_rub,
                amount_value,
            )
            return False

    upgraded = await activate_subscription_record(db, sub, target_user, settings=settings)
    await _reload_user_plan(db, target_user)
    return upgraded and target_user.plan == Plan.PRO


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
        expected_user=user,
    ):
        return await _activation_success(db, user, payment_id=payment_id, source=source)
    return None


async def _try_payment_id_for_user(
    db: AsyncSession,
    user: User,
    payment_id: str,
    *,
    settings: Settings,
    source: str,
) -> dict[str, Any] | None:
    payment_id = payment_id.strip()
    if not payment_id or payment_id.startswith("stub-"):
        return None
    try:
        payment = await get_payment(payment_id, settings)
    except YooKassaError:
        logger.warning("Could not fetch YooKassa payment %s for user %s", payment_id, user.id)
        return None
    if payment.get("status") != "succeeded":
        return None
    if not payment_matches_user(payment, user):
        logger.info("Skip payment %s for user %s — metadata/email mismatch", payment_id, user.id)
        return None
    return await _try_activate_payment(
        db, user, payment_id, payment, settings=settings, source=source
    )


async def _scan_yookassa_for_user(
    db: AsyncSession,
    user: User,
    *,
    settings: Settings,
) -> dict[str, Any] | None:
    created_gte = datetime.now(timezone.utc) - timedelta(days=90)
    user_id_str = str(user.id)

    try:
        items = await list_all_payments(
            created_gte=created_gte,
            status="succeeded",
            metadata={"user_id": user_id_str},
            settings=settings,
        )
    except YooKassaError:
        logger.warning("YooKassa metadata filter failed for user %s, falling back to scan", user.id)
        items = []

    if not items:
        try:
            items = await list_all_payments(
                created_gte=created_gte,
                status="succeeded",
                settings=settings,
            )
        except YooKassaError as e:
            logger.exception("YooKassa list payments failed for user %s", user.id)
            raise e

    seen: set[str] = set()
    for payment in items:
        if payment.get("status") != "succeeded":
            continue
        if not payment_matches_user(payment, user):
            continue
        payment_id = str(payment.get("id") or "")
        if not payment_id or payment_id in seen:
            continue
        seen.add(payment_id)

        full_payment = payment
        if not (payment.get("metadata") or {}).get("user_id") and not (payment.get("receipt") or {}).get("customer"):
            try:
                full_payment = await get_payment(payment_id, settings)
            except YooKassaError:
                continue
            if not payment_matches_user(full_payment, user):
                continue

        activated = await _try_activate_payment(
            db, user, payment_id, full_payment, settings=settings, source="yookassa_scan"
        )
        if activated:
            logger.info("Recovered Pro for user %s via YooKassa scan, payment %s", user.id, payment_id)
            return activated
    return None


def _recent_processing_pending(
    pending: list[Subscription],
    payments_by_id: dict[str, dict[str, Any]],
    *,
    now: datetime,
) -> bool:
    threshold = now - RECENT_PENDING_WINDOW
    for sub in pending:
        created_at = sub.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at < threshold:
            continue
        payment_id = (sub.yookassa_payment_id or "").strip()
        if not payment_id or payment_id.startswith("stub-"):
            continue
        payment = payments_by_id.get(payment_id)
        if payment and payment.get("status") in PAYMENT_PROCESSING_STATUSES:
            return True
    return False


async def recover_pro_for_user(
    db: AsyncSession,
    user: User,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Restore Pro after YooKassa payment:
    1) check all subscription records in DB
    2) scan succeeded payments in YooKassa by user_id / receipt email
    """
    settings = settings or get_settings()
    if user.plan == Plan.PRO:
        return {"ok": True, "plan": "pro", "already_active": True}

    subscriptions = await find_user_subscriptions(db, user.id)
    pending = [sub for sub in subscriptions if sub.status == SubscriptionStatus.PENDING]
    payments_by_id: dict[str, dict[str, Any]] = {}

    payment_ids: list[str] = []
    for sub in subscriptions:
        payment_id = (sub.yookassa_payment_id or "").strip()
        if payment_id and not payment_id.startswith("stub-"):
            payment_ids.append(payment_id)

    for payment_id in payment_ids:
        try:
            payments_by_id[payment_id] = await get_payment(payment_id, settings)
        except YooKassaError:
            logger.warning("Could not fetch YooKassa payment %s for user %s", payment_id, user.id)

    for payment_id, payment in payments_by_id.items():
        if payment.get("status") != "succeeded":
            continue
        activated = await _try_activate_payment(
            db, user, payment_id, payment, settings=settings, source="subscription_record"
        )
        if activated:
            return activated

    active_subs = [sub for sub in subscriptions if sub.status == SubscriptionStatus.ACTIVE]
    for sub in active_subs:
        payment_id = (sub.yookassa_payment_id or "").strip()
        payment = payments_by_id.get(payment_id) if payment_id else None
        if payment is not None and payment.get("status") not in (None, "succeeded"):
            continue
        await activate_pro_for_user(db, user, settings=settings)
        if sub.activated_at is None:
            sub.activated_at = datetime.now(timezone.utc)
        activated = await _activation_success(
            db,
            user,
            payment_id=payment_id or str(sub.id),
            source="active_subscription_resync",
        )
        if activated:
            logger.info(
                "Resynced Pro for user %s from active subscription %s (payment %s)",
                user.id,
                sub.id,
                payment_id or "—",
            )
            return activated

    try:
        activated = await _scan_yookassa_for_user(db, user, settings=settings)
        if activated:
            return activated
    except YooKassaError as e:
        return {
            "ok": False,
            "message": f"Не удалось проверить платежи в ЮKassa: {e}",
        }

    now = datetime.now(timezone.utc)
    if _recent_processing_pending(pending, payments_by_id, now=now):
        return {
            "ok": False,
            "status": "pending",
            "message": "Оплата ещё обрабатывается. Подождите 1–2 минуты и нажмите «проверить оплату» в профиле.",
        }

    canceled_count = sum(
        1
        for sub in pending
        if payments_by_id.get((sub.yookassa_payment_id or "").strip(), {}).get("status") == "canceled"
    )
    if pending and canceled_count == len(pending):
        return {
            "ok": False,
            "message": "Оплата не завершена. Если деньги списались — напишите в поддержку.",
        }

    return {
        "ok": False,
        "message": "Успешная оплата не найдена. Если деньги списались — напишите в поддержку.",
    }
