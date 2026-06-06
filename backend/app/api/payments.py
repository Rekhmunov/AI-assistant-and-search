import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis
from app.core.request_meta import consent_request_meta
from app.core.request_security import verify_allowed_origin
from app.schemas.payments import ProPaymentCreateRequest
from app.services.legal_documents import ConsentMeta, ensure_default_documents, record_consent
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import Plan, User
from app.services.app_settings import get_setting
from app.services.subscription_activation import activate_from_yookassa_payment, recover_pro_for_user
from app.services.yookassa import YooKassaError, create_payment, format_yookassa_error, get_payment

import redis.asyncio as redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


async def _save_pending_subscription(
    *,
    user_id: uuid.UUID,
    payment_id: str,
    amount_rub: int,
) -> None:
    """Persist subscription in a fresh DB session (after external YooKassa call)."""
    async with async_session_factory() as db:
        sub = Subscription(
            user_id=user_id,
            yookassa_payment_id=payment_id,
            status=SubscriptionStatus.PENDING,
            amount_rub=amount_rub,
        )
        db.add(sub)
        await db.commit()


@router.post("/create")
async def create_pro_payment(
    request: Request,
    body: ProPaymentCreateRequest,
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create YooKassa payment for Pro subscription."""
    verify_allowed_origin(request)
    settings = get_settings()
    return_url = f"{settings.public_web_url.rstrip('/')}/profile?payment=success"

    ip_address, ua = consent_request_meta(request)
    await ensure_default_documents(db)
    try:
        await record_consent(
            db,
            user,
            slug="offer",
            version_id=body.offer_version_id,
            meta=ConsentMeta(
                source="pro_payment",
                consent_method="checkbox",
                ip_address=ip_address,
                user_agent=ua,
            ),
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Подтвердите актуальную публичную оферту.",
        ) from exc

    async with async_session_factory() as db:
        pro_price_rub = int(await get_setting("pro_price_rub", db, redis_client, settings))
        pro_purchase_disabled = bool(await get_setting("pro_purchase_disabled", db, redis_client, settings))
    if pro_purchase_disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Покупка Pro временно недоступна. Попробуйте позже.",
        )
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
        if settings.environment.strip().lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Оплата временно недоступна. Обратитесь в поддержку.",
            )
        payment_id = f"stub-{uuid.uuid4()}"
        try:
            await _save_pending_subscription(
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
            detail=format_yookassa_error(str(e)),
        ) from e

    try:
        await _save_pending_subscription(
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
                "После оплаты откройте профиль — тариф активируется автоматически."
            ),
        ) from e

    return {
        "payment_id": result["payment_id"],
        "confirmation_url": result["confirmation_url"],
        "dev_mode": False,
    }


@router.post("/confirm")
async def confirm_pro_payment(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Подтвердить оплату после возврата с YooKassa (если webhook не успел).
    Проверяет все pending-подписки и при необходимости ищет платёж в ЮKassa по user_id.
    """
    settings = get_settings()
    if not settings.yookassa_shop_id.strip() or not settings.yookassa_secret_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="YooKassa не настроена")

    result = await recover_pro_for_user(db, user, settings=settings)
    if result.get("ok"):
        await db.refresh(user)
        return result
    return result


@router.post("/webhook")
async def yookassa_webhook(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    """Handle YooKassa payment notifications (verified via YooKassa API)."""
    settings = get_settings()
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        logger.warning("YooKassa webhook: invalid JSON")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from None

    event = body.get("event")
    obj = body.get("object") or {}
    payment_id = obj.get("id")

    logger.info("YooKassa webhook event=%s payment_id=%s", event, payment_id)

    if event != "payment.succeeded" or not payment_id:
        return {"ok": True}

    if not settings.yookassa_shop_id.strip() or not settings.yookassa_secret_key.strip():
        logger.warning("YooKassa webhook ignored: credentials not configured (payment_id=%s)", payment_id)
        return {"ok": True}

    try:
        verified_payment = await get_payment(str(payment_id), settings)
    except YooKassaError as e:
        err = str(e)
        if "HTTP 404" in err:
            logger.warning("YooKassa webhook: payment %s not found in YooKassa", payment_id)
            return {"ok": True}
        logger.warning("YooKassa webhook: could not verify payment %s: %s", payment_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment verification temporarily unavailable",
        ) from e

    if verified_payment.get("status") != "succeeded":
        logger.info(
            "YooKassa webhook: payment %s status=%s — skip activation",
            payment_id,
            verified_payment.get("status"),
        )
        return {"ok": True}

    activated = await activate_from_yookassa_payment(
        db,
        payment_id=str(payment_id),
        payment_object=verified_payment,
        settings=settings,
    )
    if not activated:
        logger.error("YooKassa webhook: activation failed for payment %s", payment_id)

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
