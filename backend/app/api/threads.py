from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SearchUserResult, get_current_user, get_db, get_existing_search_user, get_redis
from app.models.message import Message, MessageRole
from app.models.message_feedback import MessageFeedback
from app.models.thread import Thread
from app.schemas.feedback import MessageFeedbackOut, reason_label
from app.models.user import Plan, User
from app.core.config import get_settings
from app.schemas.thread import (
    AnswerStatusOut,
    EntityImageOut,
    MessageAttachmentOut,
    MessageOut,
    SourceOut,
    ThreadBulkDeleteIn,
    ThreadBulkDeleteOut,
    ThreadDetail,
    ThreadListItem,
    ThreadUpdate,
)
from app.services.search_pending import STALE_AFTER_SEC, get_search_pending
import redis.asyncio as redis
from app.services.message_attachments import message_attachments_out

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
    q = (
        select(Thread)
        .where(Thread.user_id == user.id, Thread.deleted_at.is_(None))
        .order_by(Thread.last_message_at.desc())
    )
    if cutoff:
        q = q.where(Thread.last_message_at >= cutoff)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/search", response_model=list[ThreadListItem])
async def search_threads(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    term = q.strip()
    if not term:
        return []

    pattern = f"%{term}%"
    cutoff = _history_cutoff(user)
    message_match = exists(
        select(Message.id).where(
            Message.thread_id == Thread.id,
            Message.content.ilike(pattern),
        )
    )

    query = (
        select(Thread)
        .where(
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
            or_(Thread.title.ilike(pattern), message_match),
        )
        .order_by(Thread.last_message_at.desc())
    )
    if cutoff:
        query = query.where(Thread.last_message_at >= cutoff)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/bulk-delete", response_model=ThreadBulkDeleteOut)
async def bulk_delete_threads(
    body: ThreadBulkDeleteIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    unique_ids = list(dict.fromkeys(body.thread_ids))
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Thread).where(
            Thread.id.in_(unique_ids),
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
        )
    )
    threads = result.scalars().all()
    for thread in threads:
        thread.deleted_at = now
    deleted = len(threads)
    return ThreadBulkDeleteOut(deleted=deleted, not_found=len(unique_ids) - deleted)


@router.get("/{thread_id}/answer-status", response_model=AnswerStatusOut)
async def get_thread_answer_status(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[SearchUserResult, Depends(get_existing_search_user)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
):
    user = actor.user
    result = await db.execute(
        select(Thread)
        .where(Thread.id == thread_id, Thread.user_id == user.id, Thread.deleted_at.is_(None))
        .options(selectinload(Thread.messages))
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    if not thread.messages:
        return AnswerStatusOut(pending=False, active=False, stale=False)

    sorted_msgs = sorted(thread.messages, key=lambda m: m.created_at)
    last = sorted_msgs[-1]
    if last.role != MessageRole.USER:
        return AnswerStatusOut(pending=False, active=False, stale=False)

    pending_raw = await get_search_pending(redis_client, thread_id)
    active = pending_raw is not None
    age_sec = (datetime.now(timezone.utc) - last.created_at).total_seconds()
    stale = not active and age_sec >= STALE_AFTER_SEC

    phase = pending_raw.get("phase") if pending_raw else None
    needs_search = pending_raw.get("needs_search") if pending_raw else None
    custom_status = pending_raw.get("custom_status") if pending_raw else None
    user_message_id_raw = pending_raw.get("user_message_id") if pending_raw else str(last.id)

    return AnswerStatusOut(
        pending=True,
        active=active,
        stale=stale,
        phase=str(phase) if phase else ("routing" if not stale else None),
        needs_search=bool(needs_search) if needs_search is not None else None,
        custom_status=str(custom_status) if custom_status else None,
        user_message_id=UUID(str(user_message_id_raw)),
        query=last.content,
    )


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[SearchUserResult, Depends(get_existing_search_user)],
):
    user = actor.user
    result = await db.execute(
        select(Thread)
        .where(Thread.id == thread_id, Thread.user_id == user.id, Thread.deleted_at.is_(None))
        .options(selectinload(Thread.messages))
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    assistant_ids = [m.id for m in thread.messages if m.role == MessageRole.ASSISTANT]
    feedback_by_message: dict = {}
    if assistant_ids:
        try:
            fb_rows = await db.execute(
                select(MessageFeedback).where(
                    MessageFeedback.user_id == user.id,
                    MessageFeedback.message_id.in_(assistant_ids),
                )
            )
            for fb in fb_rows.scalars().all():
                feedback_by_message[fb.message_id] = fb
        except ProgrammingError:
            await db.rollback()

    settings = get_settings()
    messages_out: list[MessageOut] = []
    for m in thread.messages:
        sources = None
        if m.sources:
            sources = [SourceOut(**s) for s in m.sources]
        images = None
        if m.images:
            images = [EntityImageOut(**img) for img in m.images]
        attachments = message_attachments_out(m.attachments, settings=settings)
        uf = None
        fb = feedback_by_message.get(m.id)
        if fb:
            uf = MessageFeedbackOut(
                rating=fb.rating.value,
                reason_code=fb.reason_code,
                reason_label=reason_label(fb.reason_code),
                comment=fb.comment,
            )
        messages_out.append(
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=sources,
                images=images,
                attachments=attachments,
                follow_up_questions=m.follow_up_questions,
                user_feedback=uf,
                created_at=m.created_at,
            )
        )

    return ThreadDetail(
        id=thread.id,
        title=thread.title,
        is_saved=thread.is_saved,
        messages=messages_out,
    )


@router.patch("/{thread_id}", response_model=ThreadListItem)
async def update_thread(
    thread_id: UUID,
    body: ThreadUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    thread.title = body.title.strip()
    await db.flush()
    await db.refresh(thread)
    return thread


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    thread.deleted_at = datetime.now(timezone.utc)


@router.post("/{thread_id}/save")
async def save_thread(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
        )
    )
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
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    thread.is_saved = False
    return {"ok": True}
