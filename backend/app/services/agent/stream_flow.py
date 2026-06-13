"""SSE-стрим обработки сообщения агента."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.limiter import RateLimiter
from app.models.user import User
from app.services.agent.agent_pending import clear_agent_pending, set_agent_pending
from app.services.agent.agent_status import (
    AgentStatusReporter,
    STATUS_THINKING,
    message_to_sse_dict,
)
from app.services.agent.flow import handle_agent_message
from app.services.sse import sse_event

logger = logging.getLogger(__name__)


async def stream_agent_message(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    thread_id: UUID,
    text: str,
    redis_client: redis.Redis,
    *,
    file_ids: list[UUID] | None = None,
) -> AsyncIterator[str]:
    reporter = AgentStatusReporter(redis_client, thread_id)
    result_box: dict = {}
    error_box: dict = {}
    user_id = user.id

    logger.info("AGENT_STREAM_START thread=%s user=%s text_len=%s", thread_id, user_id, len(text or ""))

    async def run() -> None:
        logger.info("AGENT_TASK_START thread=%s", thread_id)
        async with async_session_factory() as task_db:
            try:
                res = await task_db.execute(
                    select(User).where(User.id == user_id, User.deleted_at.is_(None))
                )
                task_user = res.scalar_one_or_none()
                if not task_user:
                    logger.warning("AGENT_TASK_NO_USER thread=%s user=%s", thread_id, user_id)
                    error_box["value"] = ValueError("user_not_found")
                    return

                logger.info("AGENT_TASK_HANDLE_START thread=%s", thread_id)
                user_msg, assistant_msg, agent = await handle_agent_message(
                    task_db,
                    task_user,
                    limiter,
                    thread_id,
                    text,
                    redis_client,
                    file_ids=file_ids,
                    on_status=reporter.callback(),
                    reporter=reporter,
                )
                logger.info("AGENT_TASK_HANDLE_DONE thread=%s status=%s", thread_id, agent.status)
                result_box["value"] = (user_msg, assistant_msg, agent)
            except ValueError as exc:
                logger.warning("AGENT_TASK_VALUE_ERROR thread=%s err=%s", thread_id, exc)
                error_box["value"] = exc
            except Exception as exc:
                logger.exception("AGENT_TASK_EXCEPTION thread=%s", thread_id)
                error_box["value"] = exc
            finally:
                logger.info("AGENT_TASK_FINALLY thread=%s has_result=%s has_error=%s",
                            thread_id, "value" in result_box, "value" in error_box)
                await reporter.close()
                await clear_agent_pending(redis_client, thread_id)

    task = asyncio.create_task(run())

    while True:
        if task.done() and reporter._queue.empty():
            break
        try:
            item = await asyncio.wait_for(reporter._queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue
        if item is not None:
            event_type, payload = item
            yield sse_event(event_type, payload)

    if "value" in error_box:
        exc = error_box["value"]
        if isinstance(exc, ValueError):
            code = str(exc)
            if code == "thread_not_found":
                yield sse_event("error", {"code": code, "message": "Тред не найден"})
                return
            if code == "agent_not_found":
                yield sse_event("error", {"code": code, "message": "Агент не найден"})
                return
            if code == "max_user_mismatch":
                yield sse_event(
                    "error",
                    {
                        "code": "agent_max_mismatch",
                        "message": "Агент привязан к другому аккаунту MAX. Создайте нового агента.",
                    },
                )
                return
            if code == "rate_limit":
                yield sse_event(
                    "error",
                    {"code": code, "message": "Достигнут дневной лимит сообщений."},
                )
                return
            if code == "text_required_with_files":
                yield sse_event(
                    "error",
                    {"code": code, "message": "Добавьте подпись к файлу — опишите что делать с этим документом."},
                )
                return
            yield sse_event("error", {"code": code, "message": "Не удалось обработать сообщение"})
            return
        yield sse_event(
            "error",
            {"code": "server_error", "message": "Сервис агента временно недоступен. Попробуйте ещё раз."},
        )
        return

    user_msg, assistant_msg, agent = result_box["value"]
    yield sse_event("user_message", message_to_sse_dict(user_msg))
    yield sse_event("assistant_message", message_to_sse_dict(assistant_msg))
    yield sse_event(
        "done",
        {
            "agent_status": agent.status,
            "agent_role": agent.role,
        },
    )


async def init_agent_pending(
    redis_client: redis.Redis,
    thread_id: UUID,
    user_message_id: UUID,
    *,
    custom_status: str | None = None,
) -> None:
    await set_agent_pending(
        redis_client,
        thread_id,
        user_message_id=user_message_id,
        phase="thinking",
        custom_status=custom_status or STATUS_THINKING,
    )
