import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, select
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.admin_permissions import require_permission
from app.core.config import get_settings
from app.models.broadcast import Broadcast
from app.models.message import Message
from app.models.message_feedback import FeedbackRating, MessageFeedback
from app.models.thread import Thread
from app.models.user import Plan, User
from app.schemas.admin import (
    DashboardMetrics,
    FeedbackDashboardBlock,
    FeedbackRecentItem,
    FeedbackRecentPage,
    FeedbackReasonStat,
)
from app.schemas.feedback import reason_label
from app.services.app_settings import get_setting

router = APIRouter(tags=["admin-dashboard"])

logger = logging.getLogger(__name__)

FEEDBACK_RECENT_DEFAULT_PAGE_SIZE = 30


def _answer_preview(content: str | None) -> str:
    preview = (content or "").strip().replace("\n", " ")
    if len(preview) > 160:
        return preview[:157] + "…"
    return preview


async def _fetch_feedback_recent_page(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
) -> FeedbackRecentPage:
    total = await db.scalar(select(func.count()).select_from(MessageFeedback)) or 0
    offset = (page - 1) * page_size
    items: list[FeedbackRecentItem] = []

    if total > 0 and offset < total:
        recent_q = (
            select(MessageFeedback, Message, Thread, User)
            .join(Message, Message.id == MessageFeedback.message_id)
            .join(Thread, Thread.id == Message.thread_id)
            .join(User, User.id == MessageFeedback.user_id)
            .order_by(MessageFeedback.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        recent_rows = await db.execute(recent_q)
        for fb, msg, thread, u in recent_rows.all():
            items.append(
                FeedbackRecentItem(
                    id=fb.id,
                    message_id=fb.message_id,
                    thread_id=thread.id,
                    user_id=u.id,
                    user_email=u.email,
                    rating=fb.rating.value,
                    reason_label=reason_label(fb.reason_code)
                    if fb.rating == FeedbackRating.DOWN
                    else None,
                    comment=fb.comment,
                    answer_preview=_answer_preview(msg.content),
                    created_at=fb.created_at,
                )
            )

    return FeedbackRecentPage(items=items, total=total, page=page, page_size=page_size)


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

    feedback_block = FeedbackDashboardBlock()
    try:
        thumbs_up = await db.scalar(
            select(func.count())
            .select_from(MessageFeedback)
            .where(MessageFeedback.rating == FeedbackRating.UP)
        )
        thumbs_down = await db.scalar(
            select(func.count())
            .select_from(MessageFeedback)
            .where(MessageFeedback.rating == FeedbackRating.DOWN)
        )
        feedback_block.thumbs_up = thumbs_up or 0
        feedback_block.thumbs_down = thumbs_down or 0
        feedback_block.recent_total = (thumbs_up or 0) + (thumbs_down or 0)

        reason_rows = await db.execute(
            select(MessageFeedback.reason_code, func.count())
            .where(MessageFeedback.rating == FeedbackRating.DOWN)
            .group_by(MessageFeedback.reason_code)
        )
        for code, cnt in reason_rows.all():
            label = reason_label(code) or (code or "—")
            feedback_block.down_by_reason.append(
                FeedbackReasonStat(reason_code=code, label=label, count=cnt or 0)
            )
        feedback_block.down_by_reason.sort(key=lambda x: -x.count)
    except ProgrammingError:
        logger.warning("message_feedback table missing — run alembic upgrade head")

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
        answer_feedback=feedback_block,
    )


@router.get("/dashboard/feedback-recent", response_model=FeedbackRecentPage)
async def dashboard_feedback_recent(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("dashboard:read")),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = FEEDBACK_RECENT_DEFAULT_PAGE_SIZE,
):
    try:
        return await _fetch_feedback_recent_page(db, page=page, page_size=page_size)
    except ProgrammingError as exc:
        logger.warning("message_feedback table missing — run alembic upgrade head")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Таблица оценок не найдена — выполните alembic upgrade head",
        ) from exc
