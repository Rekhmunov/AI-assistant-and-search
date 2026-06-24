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
    AgentThreadCreateIn,
    AgentThreadCreateOut,
)
from app.schemas.thread import MessageOut, ThreadListItem
from app.services.agent.access import require_agent_eligible
from app.services.agent.activity_log import list_agent_activity_logs
from app.services.agent.flow import create_agent_thread
from app.services.agent.stream_flow import stream_agent_message
from app.services.agent.lifecycle import get_agent_for_thread
from app.services.agent.template_visibility import get_template_visibility, is_template_visible_for_user
from app.services.agent.templates import TEMPLATE_TITLES
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
    body: AgentThreadCreateIn | None = None,
):
    require_agent_eligible(user)
    template = (body.template if body else None) or None

    # Защита от дубликата: если ассистент уже активен — редиректим на него
    if template == "assistant":
        from app.services.agent.flow import find_active_assistant_agent
        from sqlalchemy import select as _select
        from app.models.thread import Thread as _Thread
        existing = await find_active_assistant_agent(db, user)
        if existing:
            thread_res = await db.execute(
                _select(_Thread).where(_Thread.id == existing.thread_id)
            )
            existing_thread = thread_res.scalar_one_or_none()
            if existing_thread:
                from app.models.message import Message as _Message
                from app.models.message import MessageRole as _MessageRole
                redirect_msg = _Message(
                    thread_id=existing_thread.id,
                    role=_MessageRole.ASSISTANT,
                    content=(
                        "✅ Личный ассистент уже активирован.\n\n"
                        "Чтобы пересоздать — деактивируйте текущего. "
                        "Для деактивации напишите **деактивировать** или **отключить**."
                    ),
                )
                db.add(redirect_msg)
                await db.flush()
                await db.commit()
                await db.refresh(existing_thread)
                await db.refresh(redirect_msg)
                return AgentThreadCreateOut(
                    thread=ThreadListItem.model_validate(existing_thread),
                    welcome_message=MessageOut.model_validate(redirect_msg),
                )

    thread, _agent, welcome = await create_agent_thread(db, user, template=template)
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


@router.get("/templates")
async def list_agent_templates(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis_client=Depends(get_redis),
):
    """Шаблоны агентов, доступные текущему пользователю."""
    require_agent_eligible(user)
    visibility = await get_template_visibility(db, redis_client)
    result = []
    # "assistant" создаётся автоматически — не показываем в списке выбора
    _AUTO_CREATED = {"assistant"}
    for tid, title in TEMPLATE_TITLES.items():
        if tid in _AUTO_CREATED:
            continue
        if is_template_visible_for_user(visibility, tid, user.id):
            result.append({"id": tid, "title": title})
    return result


@router.get("/list")
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Список всех агентов пользователя с карточками для страницы /agents."""
    require_agent_eligible(user)
    from sqlalchemy import select
    from app.models.agent import AgentInstance, AgentStatus
    from app.models.thread import Thread
    from app.services.agent.constants import SUPPORTED_ROLE_LABELS

    result = await db.execute(
        select(AgentInstance, Thread)
        .join(Thread, Thread.id == AgentInstance.thread_id)
        .where(
            AgentInstance.user_id == user.id,
            AgentInstance.status != AgentStatus.CANCELLED.value,
            Thread.deleted_at.is_(None),
        )
        .order_by(AgentInstance.created_at.desc())
    )
    rows = result.all()

    agents_out = []
    for agent, thread in rows:
        cfg = dict(agent.config or {})
        agents_out.append({
            "id": str(agent.id),
            "thread_id": str(agent.thread_id),
            "status": agent.status,
            "role": agent.role,
            "role_label": SUPPORTED_ROLE_LABELS.get(agent.role or "", agent.role or "Агент"),
            "title": thread.title or "Агент",
            "instruction_text": agent.instruction_text or "",
            "max_chat_id": agent.max_chat_id,
            "schedule_text": cfg.get("schedule_text"),
            "next_run_at": cfg.get("next_run_at"),
            "last_dispatch_error": cfg.get("last_dispatch_error"),
            "created_at": agent.created_at.isoformat(),
            "updated_at": agent.updated_at.isoformat(),
        })
    return {"agents": agents_out}


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


@router.patch("/threads/{thread_id}/config")
async def patch_agent_config(
    thread_id: UUID,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Update agent config from settings form (poster agent)."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    cfg = dict(agent.config or {})
    for key, value in body.items():
        if key.startswith("poster_") or key in ("support_instructions",):
            cfg[key] = value
    agent.config = cfg
    await db.commit()
    return {"ok": True, "config": {k: v for k, v in cfg.items() if k.startswith("poster_")}}


@router.post("/threads/{thread_id}/generate-post")
async def generate_poster_post(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis_client: redis.Redis = Depends(get_redis),
):
    """Generate a one-off post for the poster agent (ignores schedule)."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    try:
        from app.services.agent.poster_executor import (
            generate_post,
            get_approval_mode,
            get_poster_channel_id,
            publish_to_channel,
            save_pending_draft,
            save_post_to_history,
            send_draft_for_approval,
            update_post_status,
            _pick_next_topic,
        )
        from app.services.providers.factory import resolve_agent_providers
        from app.services.bot import MaxBotService
        import uuid as _uuid

        topic = _pick_next_topic(agent)
        llm, _, _, _, _ = await resolve_agent_providers(db, redis_client)
        post_text = await generate_post(agent, topic, llm)
        post_id = str(_uuid.uuid4())

        save_post_to_history(agent, post_id=post_id, topic=topic, text=post_text, status="draft")

        approval_mode = get_approval_mode(agent)
        channel_id = get_poster_channel_id(agent)
        approval_chat_id = agent.max_chat_id
        bot = MaxBotService()

        if approval_mode == "auto" and channel_id:
            ok = await publish_to_channel(bot, channel_id=channel_id, text=post_text)
            if ok:
                update_post_status(agent, post_id, "published")
                await db.commit()
                return {"ok": True, "mode": "published", "topic": topic}
            return {"ok": False, "error": "Не удалось опубликовать в канал. Проверьте права бота."}
        elif approval_chat_id:
            save_pending_draft(agent, post_id=post_id, topic=topic, text=post_text)
            msg_id = await send_draft_for_approval(
                agent, db, bot,
                approval_chat_id=approval_chat_id,
                post_id=post_id, topic=topic, text=post_text,
            )
            save_pending_draft(agent, post_id=post_id, topic=topic, text=post_text, draft_message_id=msg_id)
            await db.commit()
            return {"ok": True, "mode": "approval", "topic": topic}
        else:
            await db.commit()
            return {"ok": False, "error": "Не настроен канал или группа для согласования"}
    except Exception as exc:
        logger.exception("generate_poster_post failed thread=%s: %s", thread_id, exc)
        return {"ok": False, "error": str(exc)[:300]}


@router.post("/threads/{thread_id}/verify-channel")
async def verify_poster_channel(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis_client: redis.Redis = Depends(get_redis),
):
    """Check if bot is admin in the configured poster channel."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    cfg = dict(agent.config or {})
    channel_id_raw = cfg.get("poster_channel_id") or ""
    if not channel_id_raw:
        return {"ok": False, "bot_is_admin": False, "error": "Канал не указан в настройках"}

    # Try to parse channel id
    try:
        channel_id = int(str(channel_id_raw).strip().lstrip("@").replace("https://max.ru/", ""))
    except ValueError:
        channel_id = None

    if not channel_id:
        # Try string-based lookup
        try:
            from app.services.agent.max_probe import resolve_channel_link, probe_max_chat
            from app.services.bot import MaxBotService
            bot = MaxBotService()
            resolved = await resolve_channel_link(str(channel_id_raw).strip(), bot=bot)
            if not resolved:
                return {"ok": False, "bot_is_admin": False, "error": f"Не удалось найти канал: {channel_id_raw}"}
            channel_id = resolved
        except Exception as exc:
            return {"ok": False, "bot_is_admin": False, "error": str(exc)[:200]}

    try:
        from app.services.agent.max_probe import probe_max_chat
        from app.services.bot import MaxBotService
        bot = MaxBotService()
        probe = await probe_max_chat(channel_id, bot=bot)
        return {
            "ok": probe.get("ok", False),
            "bot_is_admin": probe.get("bot_is_admin", False),
            "chat_name": probe.get("chat_name", ""),
            "error": probe.get("error", "") if not probe.get("ok") else "",
        }
    except Exception as exc:
        return {"ok": False, "bot_is_admin": False, "error": str(exc)[:200]}
