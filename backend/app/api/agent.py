import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_db, get_rate_limiter, get_redis
from app.core.limiter import RateLimiter
from app.models.user import User
from app.schemas.agent import AgentMessageIn, AgentMessageOut, AgentThreadCreateOut
from app.schemas.thread import MessageOut, ThreadListItem
from app.services.agent.access import require_agent_eligible
from app.services.agent.flow import create_agent_thread, handle_agent_message
import redis.asyncio as redis
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


@router.post("/threads/{thread_id}/messages", response_model=AgentMessageOut)
async def post_agent_message(
    thread_id: UUID,
    body: AgentMessageIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
):
    require_agent_eligible(user)

    try:
        user_msg, assistant_msg, agent = await handle_agent_message(
            db,
            user,
            limiter,
            thread_id,
            body.text,
            redis_client,
            file_ids=body.file_ids,
        )
    except ValueError as exc:
        await db.rollback()
        code = str(exc)
        if code == "thread_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
        if code == "agent_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")
        if code == "max_user_mismatch":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "agent_max_mismatch",
                    "message": "Агент привязан к другому аккаунту MAX. Создайте нового агента.",
                },
            )
        if code == "rate_limit":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Достигнут дневной лимит сообщений.",
            )
        logger.warning("Agent message error: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось обработать сообщение")
    except Exception as exc:
        await db.rollback()
        logger.exception("Agent message unhandled error thread=%s", thread_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис агента временно недоступен. Попробуйте ещё раз.",
        ) from exc

    return AgentMessageOut(
        user_message=MessageOut.model_validate(user_msg),
        assistant_message=MessageOut.model_validate(assistant_msg),
        agent_status=agent.status,
        agent_role=agent.role,
    )
