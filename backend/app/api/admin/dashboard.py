import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import distinct, func, select
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.admin_permissions import require_permission
from app.core.config import get_settings
from app.models.broadcast import Broadcast
from app.models.message import Message
from app.models.thread import Thread
from app.models.user import Plan, User
from app.schemas.admin import DashboardMetrics
from app.services.app_settings import get_setting

router = APIRouter(tags=["admin-dashboard"])


logger = logging.getLogger(__name__)


@router.get("/dashboard", response_model=DashboardMetrics)
async def dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("dashboard:read")),
):
    settings = get_settings()
    redis = await get_redis()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(hours=24)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        users_total = await db.scalar(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        )
        users_new_7d = await db.scalar(
            select(func.count()).select_from(User).where(
                User.deleted_at.is_(None), User.created_at >= week_ago
            )
        )
        users_pro = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None), User.plan == Plan.PRO.value)
        )
        users_active_24h = await db.scalar(
            select(func.count(distinct(Thread.user_id)))
            .select_from(Thread)
            .where(Thread.last_message_at >= day_ago)
        )
        broadcasts_total = await db.scalar(select(func.count()).select_from(Broadcast))
        messages_today = await db.scalar(
            select(func.count()).select_from(Message).where(Message.created_at >= today_start)
        )
    except ProgrammingError as exc:
        logger.exception("Dashboard DB schema error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База не обновлена. Выполните: docker compose -f docker-compose.prod.yml exec backend alembic upgrade head",
        ) from exc
    except DBAPIError as exc:
        logger.exception("Dashboard DBAPI error")
        hint = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка БД при загрузке метрик: {hint[:200]}",
        ) from exc
    except Exception as exc:
        logger.exception("Dashboard metrics query failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка загрузки метрик: {type(exc).__name__}",
        ) from exc

    redis_ok = True
    try:
        await redis.ping()
    except Exception:
        redis_ok = False

    maintenance = await get_setting("maintenance_mode", db, redis, settings)

    return DashboardMetrics(
        users_total=users_total or 0,
        users_new_7d=users_new_7d or 0,
        users_pro=users_pro or 0,
        users_active_24h=users_active_24h or 0,
        broadcasts_total=broadcasts_total or 0,
        messages_today=messages_today or 0,
        searches_today_estimate=messages_today or 0,
        yandex_configured=settings.yandex_configured,
        redis_ok=redis_ok,
        maintenance_mode=bool(maintenance),
    )
