from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.config import get_settings
from app.services.app_settings import get_setting

import redis.asyncio as redis

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/public")
async def public_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
):
    """Public app settings for frontend (price, limits display)."""
    settings = get_settings()
    pro_price_rub = int(await get_setting("pro_price_rub", db, redis_client, settings))
    return {"pro_price_rub": pro_price_rub}
