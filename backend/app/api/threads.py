from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SearchUserResult, get_current_user, get_db, get_existing_search_user, get_redis
from app.models.agent import AgentInstance
from app.models.message import Message, MessageRole
from app.models.message_feedback import MessageFeedback
from app.models.thread import Thread, ThreadType
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
from app.services.agent.agent_pending import clear_agent_pending, get_agent_pending
from app.services.search_pending import (
    STALE_AFTER_SEC,
    clear_search_pending,
    get_search_pending,
    is_pending_zombie,
    pending_active_seconds,
)
from app.services.service_incidents import record_service_incident
import redis.asyncio as redis
from app.models.uploaded_file import UploadedFile
from app.services.message_attachments import message_attachments_out
from app.services.agent.lifecycle import on_thread_soft_deleted
from app.services.upload_lifecycle import purge_generated_files_exclusive_to_threads

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
    from sqlalchemy import case, nulls_last
    # Hide assistant threads (auto-created, not user-managed).
    # Hide sub-reminder threads (is_sub_reminder=true in config, managed via hub panel).
    hidden_thread_ids = select(AgentInstance.thread_id).where(
        AgentInstance.user_id == user.id,
        or_(
            AgentInstance.config["template"].astext == "assistant",
            AgentInstance.config["is_sub_reminder"].astext == "true",
            AgentInstance.config["is_new"].astext == "true",
        ),
    )
    q = (
        select(Thread)
        .where(
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
            Thread.id.not_in(hidden_thread_ids),
        )
        .order_by(
            # Закреплённые — всегда первые, сортируются по pinned_at DESC
            nulls_last(Thread.pinned_at.desc()),
            Thread.last_message_at.desc(),
        )
    )
    if cutoff:
        q = q.where(
            (Thread.last_message_at >= cutoff) | Thread.pinned_at.isnot(None)
        )
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

    hidden_thread_ids_search = select(AgentInstance.thread_id).where(
        AgentInstance.user_id == user.id,
        or_(
            AgentInstance.config["template"].astext == "assistant",
            AgentInstance.config["is_sub_reminder"].astext == "true",
        ),
    )
    query = (
        select(Thread)
        .where(
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
            Thread.id.not_in(hidden_thread_ids_search),
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
    thread_ids = {thread.id for thread in threads}
    for thread in threads:
        thread.deleted_at = now
        await on_thread_soft_deleted(db, thread)
    if thread_ids:
        await purge_generated_files_exclusive_to_threads(db, user.id, thread_ids)
    await db.commit()
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

    is_agent_thread = thread.thread_type == ThreadType.AGENT
    pending_raw = (
        await get_agent_pending(redis_client, thread_id)
        if is_agent_thread
        else await get_search_pending(redis_client, thread_id)
    )
    age_sec = (datetime.now(timezone.utc) - last.created_at).total_seconds()

    if pending_raw and is_pending_zombie(pending_raw):
        preview = (last.content or "")[:120]
        await record_service_incident(
            redis_client,
            service="glosix_search",
            kind="stale_pending",
            message=f"Зависший поиск сброшен (thread={thread_id}, query={preview!r})",
        )
        if is_agent_thread:
            await clear_agent_pending(redis_client, thread_id)
        else:
            await clear_search_pending(redis_client, thread_id)
        pending_raw = None

    active = pending_raw is not None
    stale = not active and age_sec >= STALE_AFTER_SEC
    active_age_sec = pending_active_seconds(pending_raw) if pending_raw else None

    phase = pending_raw.get("phase") if pending_raw else None
    if is_agent_thread and active and not phase:
        phase = "routing"
    needs_search = pending_raw.get("needs_search") if pending_raw else None
    custom_status = pending_raw.get("custom_status") if pending_raw else None
    user_message_id_raw = pending_raw.get("user_message_id") if pending_raw else str(last.id)

    return AnswerStatusOut(
        pending=True,
        active=active,
        stale=stale,
        active_age_sec=active_age_sec,
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
    attachment_file_ids: set[UUID] = set()
    for m in thread.messages:
        if not m.attachments:
            continue
        for item in m.attachments:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            if not raw_id:
                continue
            try:
                attachment_file_ids.add(UUID(str(raw_id)))
            except ValueError:
                continue

    files_by_id: dict[UUID, UploadedFile] = {}
    if attachment_file_ids:
        file_rows = await db.execute(
            select(UploadedFile).where(
                UploadedFile.user_id == user.id,
                UploadedFile.id.in_(attachment_file_ids),
            )
        )
        files_by_id = {row.id: row for row in file_rows.scalars().all()}

    messages_out: list[MessageOut] = []
    for m in thread.messages:
        sources = None
        if m.sources:
            sources = [SourceOut(**s) for s in m.sources]
        images = None
        if m.images:
            images = [EntityImageOut(**img) for img in m.images]
        attachments = message_attachments_out(
            m.attachments,
            settings=settings,
            files_by_id=files_by_id,
        )
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

    # For agent threads, include poster_enabled and other agent config
    # so the frontend can restore toggle state without requiring re-save
    agent_config: dict | None = None
    if thread.thread_type and "agent" in str(thread.thread_type):
        try:
            from app.services.agent.lifecycle import get_agent_for_thread
            agent = await get_agent_for_thread(db, thread.id)
            if agent and agent.config:
                cfg = dict(agent.config)
                template = cfg.get("template", "")
                if template == "secretary":
                    # Secretary: expose categories, group info, enabled flag
                    _SECRETARY_SAFE = frozenset({
                        "template", "support_instructions", "max_chat_id",
                        "task_mode", "secretary_enabled", "timezone",
                        "bot_is_group_admin", "bot_can_read_messages",
                    })
                    agent_config = {k: v for k, v in cfg.items() if k in _SECRETARY_SAFE}
                    # Also expose agent.max_chat_id from DB field (set by onboarding)
                    if agent.max_chat_id and not agent_config.get("max_chat_id"):
                        agent_config["max_chat_id"] = agent.max_chat_id
                    agent_config["agent_status"] = agent.status
                elif template == "expert":
                    # Expert: expose instruction field
                    agent_config = {
                        "template": "expert",
                        "expert_instruction": cfg.get("expert_instruction", ""),
                        "agent_status": agent.status,
                    }
                else:
                    # Only expose poster_* fields (safe subset of agent config)
                    agent_config = {k: v for k, v in cfg.items() if k.startswith("poster_") or k == "template"}
        except Exception:
            pass

    return ThreadDetail(
        id=thread.id,
        title=thread.title,
        thread_type=thread.thread_type,
        agent_seq=thread.agent_seq,
        is_saved=thread.is_saved,
        messages=messages_out,
        agent_config=agent_config,
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
    if body.title is not None:
        thread.title = body.title.strip()
    if body.pinned is not None:
        from datetime import datetime, timezone
        thread.pinned_at = datetime.now(timezone.utc) if body.pinned else None
    await db.flush()
    await db.commit()
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
    await on_thread_soft_deleted(db, thread)
    await purge_generated_files_exclusive_to_threads(db, user.id, {thread_id})
    await db.commit()


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
