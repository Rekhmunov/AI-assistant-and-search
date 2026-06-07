from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.config import get_settings
from app.services.app_settings import get_setting

import redis.asyncio as redis

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/public")
async def public_config(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
):
    """Public app settings for frontend (price, limits display)."""
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    pro_price_rub = int(await get_setting("pro_price_rub", db, redis_client, settings))
    pro_purchase_disabled = bool(await get_setting("pro_purchase_disabled", db, redis_client, settings))
    metrica_id = str(await get_setting("yandex_metrica_counter_id", db, redis_client, settings)).strip()
    webmaster_code = str(await get_setting("yandex_webmaster_verification", db, redis_client, settings)).strip().lower()
    return {
        "pro_price_rub": pro_price_rub,
        "pro_purchase_disabled": pro_purchase_disabled,
        "yandex_metrica_counter_id": metrica_id or None,
        "yandex_webmaster_verification": webmaster_code or None,
    }
