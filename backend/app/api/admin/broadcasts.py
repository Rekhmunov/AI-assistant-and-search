from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.admin_permissions import require_permission
from app.models.admin_user import AdminUser
from app.models.broadcast import Broadcast, BroadcastAudience, BroadcastLog, BroadcastStatus
from app.models.user import Plan, User
from app.schemas.admin import AudiencePreview, BroadcastCreate, BroadcastLogOut, BroadcastOut
from app.services.admin_audit import log_admin_action
from app.workers.broadcast_tasks import send_broadcast_task

router = APIRouter(prefix="/broadcasts", tags=["admin-broadcasts"])


async def _audience_count(db: AsyncSession, audience: BroadcastAudience) -> int:
    q = select(func.count()).select_from(User).where(User.deleted_at.is_(None))
    if audience == BroadcastAudience.FREE:
        q = q.where(User.plan == Plan.FREE)
    elif audience == BroadcastAudience.PRO:
        q = q.where(User.plan == Plan.PRO)
    return int(await db.scalar(q) or 0)


@router.get("/audience-preview", response_model=AudiencePreview)
async def audience_preview(
    db: Annotated[AsyncSession, Depends(get_db)],
    audience: BroadcastAudience = Query(default=BroadcastAudience.ALL),
    _admin=Depends(require_permission("broadcasts:read")),
):
    count = await _audience_count(db, audience)
    return AudiencePreview(audience=audience, recipient_count=count)


@router.get("", response_model=list[BroadcastOut])
async def list_broadcasts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("broadcasts:read")),
):
    result = await db.execute(select(Broadcast).order_by(Broadcast.created_at.desc()).limit(50))
    return result.scalars().all()


@router.post("", response_model=BroadcastOut)
async def create_broadcast(
    body: BroadcastCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    broadcast = Broadcast(text=body.text, audience=body.audience, status=BroadcastStatus.DRAFT)
    db.add(broadcast)
    await db.flush()
    await log_admin_action(
        db,
        admin=admin,
        action="broadcast.create",
        resource_type="broadcast",
        resource_id=str(broadcast.id),
        details={"audience": body.audience.value, "text_len": len(body.text)},
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return broadcast


@router.get("/{broadcast_id}/logs", response_model=list[BroadcastLogOut])
async def broadcast_logs(
    broadcast_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("broadcasts:read")),
):
    result = await db.execute(
        select(BroadcastLog)
        .where(BroadcastLog.broadcast_id == broadcast_id)
        .order_by(BroadcastLog.created_at.desc())
        .limit(200)
    )
    return result.scalars().all()


@router.post("/{broadcast_id}/send")
async def send_broadcast(
    broadcast_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("broadcasts:write"))],
):
    redis = await get_redis()
    rate_key = "admin:broadcast:hourly"
    sent_hourly = await redis.incr(rate_key)
    if sent_hourly == 1:
        await redis.expire(rate_key, 3600)
    if sent_hourly > 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Broadcast rate limit")

    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()
    if not broadcast:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broadcast not found")
    if broadcast.status == BroadcastStatus.SENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already sending")

    broadcast.status = BroadcastStatus.SENDING
    send_broadcast_task.delay(str(broadcast_id))
    await log_admin_action(
        db,
        admin=admin,
        action="broadcast.send",
        resource_type="broadcast",
        resource_id=str(broadcast_id),
        details={"audience": broadcast.audience.value},
        ip_address=request.client.host if request.client else None,
    )
    return {"ok": True, "broadcast_id": str(broadcast_id)}
