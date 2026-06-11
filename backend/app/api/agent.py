import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, get_db, get_rate_limiter, get_redis
from app.core.database import async_session_factory
from app.core.limiter import RateLimiter
from app.models.user import User
from app.schemas.agent import (
    AgentActivityLogOut,
    AgentActivityLogsOut,
    AgentMessageIn,
    AgentThreadCreateOut,
)
from app.schemas.thread import MessageOut, ThreadListItem
from app.services.agent.access import require_agent_eligible
from app.services.agent.activity_log import list_agent_activity_logs
from app.services.agent.flow import create_agent_thread
from app.services.agent.stream_flow import stream_agent_message
from app.services.agent.lifecycle import get_agent_for_thread
from app.models.thread import Thread, ThreadType
import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/threads", response_model=AgentThreadCreateOut)
async def create_agent_thread_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    require_agent_eligible(user)

    thread, _agent, welcome = await create_agent_thread(db, user)
    await db.commit()
    await db.refresh(thread)
    await db.refresh(welcome)
    return AgentThreadCreateOut(
        thread=ThreadListItem.model_validate(thread),
        welcome_message=MessageOut.model_validate(welcome),
    )


@router.post("/threads/{thread_id}/messages")
async def post_agent_message(
    thread_id: UUID,
    body: AgentMessageIn,
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
):
    require_agent_eligible(user)
    user_id = user.id

    stream_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    async def event_generator():
        async with async_session_factory() as db:
            try:
                result = await db.execute(
                    select(User).where(User.id == user_id, User.deleted_at.is_(None))
                )
                stream_user = result.scalar_one_or_none()
                if not stream_user:
                    from app.services.sse import sse_event

                    yield sse_event("error", {"code": "not_found", "message": "Пользователь не найден"})
                    return
                async for event in stream_agent_message(
                    db,
                    stream_user,
                    limiter,
                    thread_id,
                    body.text,
                    redis_client,
                    file_ids=body.file_ids,
                ):
                    yield event
            except Exception:
                await db.rollback()
                logger.exception("Agent SSE stream failed thread=%s", thread_id)
                from app.services.sse import sse_event

                yield sse_event(
                    "error",
                    {
                        "code": "server_error",
                        "message": "Сервис агента временно недоступен. Попробуйте ещё раз.",
                    },
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=stream_headers,
    )


@router.get("/threads/{thread_id}/activity-logs", response_model=AgentActivityLogsOut)
async def get_agent_activity_logs(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    require_agent_eligible(user)
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
            Thread.thread_type == ThreadType.AGENT,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    rows = await list_agent_activity_logs(db, thread_id=thread_id, user_id=user.id)
    return AgentActivityLogsOut(items=[AgentActivityLogOut.model_validate(r) for r in rows])
