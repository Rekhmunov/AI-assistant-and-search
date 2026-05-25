from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SearchUserResult, get_current_user, get_db, get_existing_search_user
from app.models.message import Message
from app.models.thread import Thread
from app.models.user import Plan, User
from app.schemas.thread import MessageOut, SourceOut, ThreadDetail, ThreadListItem

router = APIRouter(prefix="/threads", tags=["threads"])


def _history_cutoff(user: User) -> datetime | None:
    if user.plan == Plan.PRO:
        return None
    return datetime.now(timezone.utc) - timedelta(days=7)


@router.get("", response_model=list[ThreadListItem])
async def list_threads(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    cutoff = _history_cutoff(user)
    q = select(Thread).where(Thread.user_id == user.id).order_by(Thread.last_message_at.desc())
    if cutoff:
        q = q.where(Thread.last_message_at >= cutoff)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[SearchUserResult, Depends(get_existing_search_user)],
):
    user = actor.user
    result = await db.execute(
        select(Thread)
        .where(Thread.id == thread_id, Thread.user_id == user.id)
        .options(selectinload(Thread.messages))
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    messages_out: list[MessageOut] = []
    for m in thread.messages:
        sources = None
        if m.sources:
            sources = [SourceOut(**s) for s in m.sources]
        messages_out.append(
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=sources,
                follow_up_questions=m.follow_up_questions,
                created_at=m.created_at,
            )
        )

    return ThreadDetail(
        id=thread.id,
        title=thread.title,
        is_saved=thread.is_saved,
        messages=messages_out,
    )


@router.post("/{thread_id}/save")
async def save_thread(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    thread.is_saved = True
    return {"ok": True}


@router.delete("/{thread_id}/save")
async def unsave_thread(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    thread.is_saved = False
    return {"ok": True}
