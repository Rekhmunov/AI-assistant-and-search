import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis
from app.core.config import get_settings
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import Plan, User
from app.services.app_settings import get_setting
from app.services.bot import MaxBotService
from app.services.yookassa import YooKassaError, create_payment

import redis.asyncio as redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


async def _save_pending_subscription(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    payment_id: str,
    amount_rub: int,
) -> None:
    """Persist subscription after external payment API call."""
    await db.execute(text("SELECT 1"))
    sub = Subscription(
        user_id=user_id,
        yookassa_payment_id=payment_id,
        status=SubscriptionStatus.PENDING,
        amount_rub=amount_rub,
    )
    db.add(sub)
    await db.flush()


@router.post("/create")
async def create_pro_payment(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Create YooKassa payment for Pro subscription."""
    settings = get_settings()
    return_url = f"{settings.public_web_url.rstrip('/')}/profile?payment=success"
    pro_price_rub = int(await get_setting("pro_price_rub", db, redis_client, settings))
    if pro_price_rub < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректная цена Pro в настройках админки",
        )

    customer_email = (user.email or "").strip()
    if not customer_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для оплаты Pro укажите email в профиле",
        )

    payment_description = f"Glosix Pro — {settings.pro_duration_days} дней"
    yookassa_configured = bool(
        settings.yookassa_shop_id.strip() and settings.yookassa_secret_key.strip()
    )

    if not yookassa_configured:
        payment_id = f"stub-{uuid.uuid4()}"
        try:
            await _save_pending_subscription(
                db,
                user_id=user.id,
                payment_id=payment_id,
                amount_rub=pro_price_rub,
            )
        except SQLAlchemyError as e:
            logger.exception("Failed to save dev subscription")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось сохранить подписку. Проверьте миграции БД (subscriptions).",
            ) from e
        return {
            "payment_id": payment_id,
            "confirmation_url": f"{return_url}&dev=1",
            "dev_mode": True,
        }

    try:
        result = await create_payment(
            amount_rub=pro_price_rub,
            description=payment_description,
            return_url=return_url,
            customer_email=customer_email,
            metadata={"user_id": str(user.id)},
            settings=settings,
        )
    except YooKassaError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Не удалось создать платёж: {e}",
        ) from e

    try:
        await _save_pending_subscription(
            db,
            user_id=user.id,
            payment_id=result["payment_id"],
            amount_rub=pro_price_rub,
        )
    except SQLAlchemyError as e:
        logger.exception(
            "Payment %s created in YooKassa but subscription save failed",
            result["payment_id"],
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Платёж в ЮKassa создан, но не сохранился в базе. "
                "Напишите в поддержку с email аккаунта."
            ),
        ) from e

    return {
        "payment_id": result["payment_id"],
        "confirmation_url": result["confirmation_url"],
        "dev_mode": False,
    }


@router.post("/webhook")
async def yookassa_webhook(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    """Handle YooKassa payment notifications."""
    settings = get_settings()
    body: dict[str, Any] = await request.json()
    event = body.get("event")
    obj = body.get("object", {})
    payment_id = obj.get("id")

    if event != "payment.succeeded" or not payment_id:
        return {"ok": True}

    result = await db.execute(
        select(Subscription).where(Subscription.yookassa_payment_id == payment_id)
    )
    sub = result.scalar_one_or_none()
    if not sub or sub.status == SubscriptionStatus.ACTIVE:
        return {"ok": True}

    sub.status = SubscriptionStatus.ACTIVE
    sub.activated_at = datetime.now(timezone.utc)

    user_result = await db.execute(select(User).where(User.id == sub.user_id))
    user = user_result.scalar_one()
    user.plan = Plan.PRO
    user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.pro_duration_days)

    if user.max_user_id:
        bot = MaxBotService()
        await bot.send_message(user.max_user_id, "Подписка Pro активирована 🎉")

    return {"ok": True}


@router.post("/dev-activate")
async def dev_activate_pro(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Development-only: activate Pro without payment."""
    settings = get_settings()
    if settings.environment == "production":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not available")
    user.plan = Plan.PRO
    user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.pro_duration_days)
    return {"ok": True, "plan": "pro"}
