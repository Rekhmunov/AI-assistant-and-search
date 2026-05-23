from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_admin_api_key
from app.models.broadcast import Broadcast, BroadcastAudience, BroadcastStatus
from app.models.user import User
from app.workers.broadcast_tasks import send_broadcast_task

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin_api_key)])


class BroadcastCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    audience: BroadcastAudience = BroadcastAudience.ALL


class BroadcastOut(BaseModel):
    id: UUID
    text: str
    audience: BroadcastAudience
    status: BroadcastStatus
    sent_count: int
    failed_count: int

    model_config = {"from_attributes": True}


class MetricsOut(BaseModel):
    users_total: int
    users_pro: int
    broadcasts_total: int


@router.get("/metrics", response_model=MetricsOut)
async def metrics(db: Annotated[AsyncSession, Depends(get_db)]):
    from app.models.user import Plan

    total = await db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None)))
    pro = await db.scalar(
        select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.plan == Plan.PRO)
    )
    broadcasts = await db.scalar(select(func.count()).select_from(Broadcast))
    return MetricsOut(users_total=total or 0, users_pro=pro or 0, broadcasts_total=broadcasts or 0)


@router.get("/broadcasts", response_model=list[BroadcastOut])
async def list_broadcasts(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(Broadcast).order_by(Broadcast.created_at.desc()).limit(50))
    return result.scalars().all()


@router.post("/broadcasts", response_model=BroadcastOut)
async def create_broadcast(body: BroadcastCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    broadcast = Broadcast(text=body.text, audience=body.audience, status=BroadcastStatus.DRAFT)
    db.add(broadcast)
    await db.flush()
    return broadcast


@router.post("/broadcasts/{broadcast_id}/send")
async def send_broadcast(broadcast_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = result.scalar_one_or_none()
    if not broadcast:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broadcast not found")
    if broadcast.status == BroadcastStatus.SENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already sending")

    broadcast.status = BroadcastStatus.SENDING
    send_broadcast_task.delay(str(broadcast_id))
    return {"ok": True, "broadcast_id": str(broadcast_id)}
