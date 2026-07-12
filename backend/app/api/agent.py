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
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
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


@router.post("/threads/{thread_id}/touch")
async def touch_agent_thread(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Снять флаг is_new при первом изменении формы (черновик → виден в истории)."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if agent and agent.config and agent.config.get("is_new"):
        from sqlalchemy.orm.attributes import flag_modified as _fm
        cfg = dict(agent.config)
        cfg.pop("is_new", None)
        agent.config = cfg
        _fm(agent, "config")
        await db.commit()
    return {"ok": True}


@router.patch("/threads/{thread_id}/config")
async def patch_agent_config(
    thread_id: UUID,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis_client: redis.Redis = Depends(get_redis),
):
    """Update agent config from settings form (poster agent)."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    # Security: these keys must ONLY be set through dedicated verified endpoints.
    # poster_channel_id → only via verify-channel (checks bot + user admin)
    # poster_pending_draft → only via generate-post / draft-action (server-controlled)
    _BLOCKED_KEYS = frozenset({
        "poster_channel_id",     # only via verify-channel (validates bot + user admin)
        "poster_pending_draft",  # only via generate-post / draft-action (server-controlled)
        "poster_history",        # only via save_post_to_history / server; was typo'd before
    })
    _MAX_POST_TEXT_LEN = 4000  # MAX API limit

    cfg = dict(agent.config or {})
    for key, value in body.items():
        if key in _BLOCKED_KEYS:
            continue  # silently ignore protected keys
        # Validate timezone
        if key == "poster_timezone":
            import zoneinfo
            try:
                zoneinfo.ZoneInfo(str(value))
            except Exception:
                continue
        # Enforce text length limits
        if key in ("poster_topics", "poster_topic_list") and isinstance(value, (str, list)):
            if isinstance(value, str) and len(value) > _MAX_POST_TEXT_LEN:
                value = value[:_MAX_POST_TEXT_LEN]
        # expert_instruction: limit to 8000 chars
        if key == "expert_instruction" and isinstance(value, str):
            value = value[:8000]
        if key.startswith("poster_") or key in ("support_instructions", "expert_instruction", "expert_use_history", "expert_use_search"):
            cfg[key] = value
    # Активируем expert-агента при первом сохранении инструкции
    if cfg.get("template") == "expert" and cfg.get("expert_instruction"):
        from app.models.agent import AgentStatus as _AS
        if agent.status in (_AS.DRAFT.value, "draft"):
            agent.status = _AS.ACTIVE.value

    # Для secretary-агента: перекомпилируем правила при изменении категорий.
    # Условие: шаблон «secretary», сохраняется support_instructions, уже есть max_chat_id.
    compiled_ok: bool | None = None
    if (
        cfg.get("template") == "secretary"
        and "support_instructions" in body
        and cfg.get("max_chat_id")
    ):
        support_instructions = str(cfg.get("support_instructions") or "").strip()
        if support_instructions:
            try:
                from app.services.providers.factory import resolve_agent_providers
                from app.services.agent.secretary_compiler import compile_secretary_rules
                llm, _, _, _, _ = await resolve_agent_providers(db, redis_client, user=user)
                rules = await compile_secretary_rules(llm, support_instructions)
                if rules:
                    cfg["compiled_rules"] = rules
                    compiled_ok = True
                    logger.info(
                        "patch_agent_config: recompiled secretary rules for agent=%s, entities=%s",
                        agent.id, len(rules.get("entities", [])),
                    )
                else:
                    compiled_ok = False
            except Exception as _ce:
                logger.warning("patch_agent_config: rule compile failed: %s", _ce)
                compiled_ok = False

    from sqlalchemy.orm.attributes import flag_modified
    cfg.pop("is_new", None)  # первое сохранение конфига — тред появляется в истории
    agent.config = cfg
    flag_modified(agent, "config")
    await db.commit()
    resp: dict = {"ok": True, "config": {k: v for k, v in cfg.items() if k.startswith("poster_") and k not in _BLOCKED_KEYS}}
    if compiled_ok is not None:
        resp["compiled_rules"] = compiled_ok
    return resp


@router.get("/threads/{thread_id}/post-history")
async def get_poster_history(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    page: int = 1,
    per_page: int = 10,
    search: str = "",
):
    """Return post history with pagination and search."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        return {"items": [], "total": 0, "page": page, "per_page": per_page}

    from app.services.agent.poster_executor import get_post_history
    history = list(reversed(get_post_history(agent)))  # latest first

    # Filter by search
    search = search.strip().lower()
    if search:
        history = [h for h in history if search in h.get("topic", "").lower() or
                   search in (h.get("text") or "").lower()]

    total = len(history)
    per_page = max(5, min(per_page, 50))
    start = (page - 1) * per_page
    items = history[start:start + per_page]

    return {"items": items, "total": total, "page": page, "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if total > 0 else 1}


@router.delete("/threads/{thread_id}/post-history/{post_id}",
               status_code=status.HTTP_204_NO_CONTENT)
async def delete_poster_history_item(
    thread_id: UUID,
    post_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Delete a single post from history."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        return

    from app.services.agent.poster_executor import delete_post_from_history
    delete_post_from_history(agent, post_id)
    await db.commit()


@router.post("/threads/{thread_id}/post-history/clear",
             status_code=status.HTTP_204_NO_CONTENT)
async def clear_poster_history(
    thread_id: UUID,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Delete multiple posts or clear all history. body: {ids?: list[str], all?: bool}"""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        return

    from app.services.agent.poster_executor import delete_post_from_history, clear_post_history
    if body.get("all"):
        clear_post_history(agent)
    else:
        for pid in (body.get("ids") or []):
            delete_post_from_history(agent, str(pid))
    await db.commit()


@router.post("/threads/{thread_id}/generate-post")
async def generate_poster_post(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: redis.Redis = Depends(get_redis),
):
    """Generate a one-off post for the poster agent (ignores schedule)."""
    # Billing: post generation uses 1 request from the daily limit
    allowed, _used, _limit = await limiter.check_search_limit(str(user.id), user.plan, user=user)
    if not allowed:
        return {"ok": False, "error": "Достигнут дневной лимит запросов. Попробуйте завтра или подключите Pro."}

    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
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
            generate_poster_image,
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

        topic_obj = _pick_next_topic(agent)
        topic = topic_obj["text"] if isinstance(topic_obj, dict) else str(topic_obj)
        llm, _, _, _, _ = await resolve_agent_providers(db, redis_client, user=user)
        post_text = await generate_post(agent, topic_obj, llm, db=db, redis_client=redis_client)
        post_id = str(_uuid.uuid4())

        save_post_to_history(agent, post_id=post_id, topic=topic, text=post_text, status="draft")

        approval_mode = get_approval_mode(agent)
        channel_id = get_poster_channel_id(agent)
        bot = MaxBotService()

        if approval_mode == "auto" and channel_id:
            # Auto-publish mode: generate image then publish immediately
            image_bytes = await generate_poster_image(agent, topic, post_text, db=db, redis_client=redis_client)
            ok = await publish_to_channel(bot, channel_id=channel_id, text=post_text, image_bytes=image_bytes)
            if ok:
                update_post_status(agent, post_id, "published")
                await db.commit()
                return {"ok": True, "mode": "published", "topic": topic, "post_text": post_text}
            return {"ok": False, "error": "Не удалось опубликовать в канал. Проверьте права бота."}
        else:
            # Manual draft: return TEXT immediately without waiting for image.
            # Frontend will call gen_image action separately to load image in background.
            cfg = dict(agent.config or {})
            wants_ai_image = str(cfg.get("poster_media") or "none").lower() == "ai"

            save_pending_draft(agent, post_id=post_id, topic=topic, text=post_text, image_file_ids=[])
            await db.commit()
            return {
                "ok": True,
                "mode": "web_draft",
                "topic": topic,
                "post_id": post_id,
                "post_text": post_text,
                "image_url": None,
                "file_id": None,
                # Signal frontend to auto-trigger image generation
                "wants_ai_image": wants_ai_image,
            }
    except Exception as exc:
        logger.exception("generate_poster_post failed thread=%s: %s", thread_id, exc)
        return {"ok": False, "error": str(exc)[:300]}


@router.get("/threads/{thread_id}/pending-draft")
async def get_pending_draft_status(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Return current pending draft for the poster agent (for thread polling)."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        return {"draft": None}

    from app.services.agent.poster_executor import get_pending_draft
    draft = get_pending_draft(agent)
    if not draft:
        return {"draft": None}

    return {
        "draft": {
            "post_id": draft.get("post_id"),
            "topic": draft.get("topic"),
            "text": draft.get("text"),
        }
    }


@router.post("/threads/{thread_id}/draft-action")
async def poster_draft_action(
    thread_id: UUID,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Handle draft actions from the web mini-app:
    action: 'approve' | 'reject' | 'regen'
    post_id: str
    """
    action = str(body.get("action", ""))
    post_id = str(body.get("post_id", ""))

    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    from app.services.agent.poster_executor import (
        get_pending_draft, clear_pending_draft, update_post_status,
        get_poster_channel_id, publish_to_channel, generate_poster_image,
        generate_post, save_post_to_history, save_pending_draft, _pick_next_topic,
        mark_draft_message_done, edit_draft_message,
        get_draft_image_file_ids, set_draft_image_file_ids,
        MAX_DRAFT_IMAGES,
    )
    from app.services.bot import MaxBotService
    from app.services.upload_storage import load_upload_bytes
    from app.models.uploaded_file import UploadedFile as _UF

    # use_as_base: create new draft from history item text (no existing draft needed)
    if action == "use_as_base":
        import uuid as _uuid_base
        new_text = str(body.get("text") or "").strip()[:4000]  # MAX API limit
        new_topic = str(body.get("topic") or "").strip()[:200]
        if not new_text:
            return {"ok": False, "error": "Текст не может быть пустым"}
        new_id = str(_uuid_base.uuid4())
        save_post_to_history(agent, post_id=new_id, topic=new_topic, text=new_text, status="draft")
        save_pending_draft(agent, post_id=new_id, topic=new_topic, text=new_text, image_file_ids=[])
        cfg_ub = dict(agent.config or {})
        wants_ai = str(cfg_ub.get("poster_media") or "none").lower() == "ai"
        await db.commit()
        return {"ok": True, "mode": "web_draft", "post_id": new_id,
                "post_text": new_text, "topic": new_topic,
                "image_url": None, "wants_ai_image": wants_ai}

    draft = get_pending_draft(agent)
    if not draft or draft.get("post_id") != post_id:
        return {"ok": False, "error": "Черновик устарел или уже обработан"}

    bot = MaxBotService()
    draft_message_id = draft.get("draft_message_id")  # for DM sync

    if action == "approve":
        channel_id = get_poster_channel_id(agent)
        if not channel_id:
            return {"ok": False, "error": "Канал не настроен"}

        # Atomic idempotency: mark draft as "publishing" before sending.
        # If another request races in, it will see the wrong post_id and bail.
        if draft.get("publishing"):
            return {"ok": False, "error": "Пост уже публикуется, подождите."}
        from app.services.agent.poster_executor import save_pending_draft as _spd
        _spd(agent, post_id=post_id, topic=draft.get("topic", ""),
             text=draft.get("text", ""), draft_message_id=draft_message_id)
        # Flag draft as "publishing" so concurrent requests bail early
        _draft_cfg = dict(agent.config or {})
        _pdr = _draft_cfg.get("poster_pending_draft", {})
        _pdr["publishing"] = True
        _draft_cfg["poster_pending_draft"] = _pdr
        from sqlalchemy.orm.attributes import flag_modified as _fm_approve
        agent.config = _draft_cfg
        _fm_approve(agent, "config")
        await db.flush()

        draft_text = draft.get("text", "")
        draft_topic = draft.get("topic", "")

        # Load all stored images for this draft
        image_file_ids = get_draft_image_file_ids(agent)
        logger.warning("POSTER_APPROVE image_file_ids=%s channel=%s", image_file_ids, channel_id)

        images_bytes_list: list[bytes] = []
        for fid in image_file_ids:
            try:
                from uuid import UUID as _UUID2
                # Always enforce user_id to prevent loading another user's files
                _uf_res = await db.execute(
                    select(_UF).where(_UF.id == _UUID2(fid), _UF.user_id == user.id)
                )
                _uf = _uf_res.scalar_one_or_none()
                if _uf and _uf.storage_key:
                    img = load_upload_bytes(_uf.storage_key)
                    if img:
                        images_bytes_list.append(img)
            except Exception as _exc:
                logger.warning("POSTER_APPROVE load image %s failed: %s", fid, _exc)

        # If no stored images, generate fresh AI image
        if not images_bytes_list:
            logger.warning("POSTER_APPROVE generating fresh image (poster_media=%s)",
                           (agent.config or {}).get("poster_media"))
            fresh = await generate_poster_image(agent, draft_topic, draft_text, db=db, redis_client=redis_client)
            if fresh:
                images_bytes_list = [fresh]

        ok = await publish_to_channel(
            bot, channel_id=channel_id, text=draft_text,
            image_bytes_list=images_bytes_list if images_bytes_list else None,
        )
        logger.warning("POSTER_APPROVE publish ok=%s images=%d", ok, len(images_bytes_list))
        if ok:
            update_post_status(agent, post_id, "published")
            clear_pending_draft(agent)
            # Edit DM message to show published status
            if draft_message_id:
                await mark_draft_message_done(
                    bot, draft_message_id=draft_message_id,
                    status_text=f"✅ Пост «{draft_topic[:60]}» опубликован в канале.",
                )
            await db.commit()
            return {"ok": True, "mode": "published"}
        # Publish failed — clear publishing flag so user can retry
        _fail_cfg = dict(agent.config or {})
        _fail_pdr = _fail_cfg.get("poster_pending_draft", {})
        _fail_pdr.pop("publishing", None)
        _fail_cfg["poster_pending_draft"] = _fail_pdr
        from sqlalchemy.orm.attributes import flag_modified as _fm_fail
        agent.config = _fail_cfg
        _fm_fail(agent, "config")
        await db.commit()
        return {"ok": False, "error": "Не удалось опубликовать. Проверьте права бота."}

    elif action == "reject":
        topic = draft.get("topic", "")
        update_post_status(agent, post_id, "rejected")
        clear_pending_draft(agent)
        # Edit DM message to show rejected status
        if draft_message_id:
            await mark_draft_message_done(
                bot, draft_message_id=draft_message_id,
                status_text=f"❌ Пост «{topic[:60]}» отклонён.",
            )
        await db.commit()
        return {"ok": True, "mode": "rejected"}

    elif action == "edit":
        new_text = str(body.get("text", "")).strip()[:4000]  # MAX API limit
        if not new_text:
            return {"ok": False, "error": "Текст не может быть пустым"}
        topic = draft.get("topic", "")
        save_pending_draft(agent, post_id=post_id, topic=topic, text=new_text)
        # Edit DM message with updated text (no image change for text-only edits)
        if draft_message_id:
            await edit_draft_message(bot, agent, draft_message_id=draft_message_id,
                                     post_id=post_id, topic=topic, text=new_text)
        await db.commit()
        return {"ok": True, "mode": "web_draft", "post_id": post_id, "post_text": new_text, "topic": topic}

    elif action == "regen":
        # Billing: text+image regen costs 1 request
        allowed, _used, _limit = await limiter.check_search_limit(str(user.id), user.plan, user=user)
        if not allowed:
            return {"ok": False, "error": "Достигнут дневной лимит запросов. Попробуйте завтра или подключите Pro."}

        from app.services.providers.factory import resolve_agent_providers
        from app.services.agent.poster_executor import _topic_text
        import uuid as _uuid
        # draft["topic"] is always str; _pick_next_topic returns dict {text, search}
        topic_raw = draft.get("topic")
        if topic_raw:
            topic_obj = topic_raw  # regen same topic (no search flag on regen)
            topic = topic_raw
        else:
            topic_obj = _pick_next_topic(agent)
            topic = _topic_text(topic_obj)
        update_post_status(agent, post_id, "rejected")
        clear_pending_draft(agent)
        try:
            llm, _, _, _, _ = await resolve_agent_providers(db, redis_client, user=user)
            new_text = await generate_post(agent, topic_obj, llm, db=db, redis_client=redis_client)
            new_id = str(_uuid.uuid4())
            save_post_to_history(agent, post_id=new_id, topic=topic, text=new_text, status="draft")
            save_pending_draft(agent, post_id=new_id, topic=topic, text=new_text, image_file_ids=[])

            # Signal DM message update (text only; frontend handles image separately)
            if draft_message_id:
                try:
                    await edit_draft_message(
                        bot, agent, draft_message_id=draft_message_id,
                        post_id=new_id, topic=topic, text=new_text,
                    )
                    save_pending_draft(agent, post_id=new_id, topic=topic,
                                       text=new_text, draft_message_id=draft_message_id)
                except Exception as _dme:
                    logger.warning("regen DM edit failed: %s", _dme)

            cfg_r = dict(agent.config or {})
            wants_ai_image = str(cfg_r.get("poster_media") or "none").lower() == "ai"

            await db.commit()
            return {"ok": True, "mode": "web_draft", "post_id": new_id, "post_text": new_text,
                    "topic": topic, "image_url": None, "wants_ai_image": wants_ai_image}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    elif action == "regen_image":
        # Billing: image regen costs 1 request
        allowed, _used, _limit = await limiter.check_search_limit(str(user.id), user.plan, user=user)
        if not allowed:
            return {"ok": False, "error": "Достигнут дневной лимит запросов. Попробуйте завтра или подключите Pro."}

        # Regenerate AI image only (keep current text)
        topic = draft.get("topic", "")
        text = draft.get("text", "")
        try:
            new_image_bytes = await generate_poster_image(agent, topic, text, db=db, redis_client=redis_client)
            if not new_image_bytes:
                # Image generation failed but draft text is intact — allow post without image
                await db.commit()
                return {
                    "ok": True,
                    "mode": "image_skipped",
                    "image_url": None,
                    "file_id": None,
                    "warning": "Не удалось сгенерировать изображение. Пост можно опубликовать без картинки.",
                }
            from app.services.image_gen_service import persist_generated_image, public_file_content_url
            import uuid as _uuid
            fid, _ = await persist_generated_image(db, user, new_image_bytes, title=topic, ttl_hours=24)
            # ADD to existing images (do not replace all)
            current_ids = get_draft_image_file_ids(agent)
            if len(current_ids) >= MAX_DRAFT_IMAGES:
                return {"ok": False, "error": f"Максимум {MAX_DRAFT_IMAGES} фото. Удалите одно."}
            set_draft_image_file_ids(agent, current_ids + [str(fid)])
            # Return base64 for immediate preview
            import base64 as _b64
            from app.services.image_bytes import detect_image_mime as _det
            _mime = _det(new_image_bytes) or "image/jpeg"
            image_url = f"data:{_mime};base64,{_b64.b64encode(new_image_bytes).decode('ascii')}"
            await db.commit()
            return {"ok": True, "mode": "image_updated", "image_url": image_url, "file_id": str(fid)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    elif action == "add_image":
        # Add an uploaded image file to draft (max 4 total)
        from uuid import UUID as _UUID3
        new_file_id = str(body.get("file_id", "")).strip()
        logger.warning("POSTER add_image file_id=%s user=%s draft_post_id=%s",
                       new_file_id, user.id, post_id)
        if not new_file_id:
            return {"ok": False, "error": "file_id не указан"}
        try:
            # Search by file id only (UUID is globally unique; upload may use a
            # different auth context than this endpoint in the MAX mini-app)
            _uf_r = await db.execute(select(_UF).where(_UF.id == _UUID3(new_file_id)))
            _uf = _uf_r.scalar_one_or_none()
            logger.warning("POSTER add_image found_file=%s file_user=%s",
                           bool(_uf), _uf.user_id if _uf else None)
            if not _uf:
                return {"ok": False, "error": "Файл не найден"}
            # Verify the file belongs to this user or another user of the same account
            if str(_uf.user_id) != str(user.id):
                logger.warning("POSTER add_image user_mismatch file_user=%s request_user=%s",
                               _uf.user_id, user.id)
                return {"ok": False, "error": "Нет доступа к этому файлу"}
        except Exception as _exc:
            logger.warning("POSTER add_image error: %s", _exc)
            return {"ok": False, "error": "Неверный file_id"}
        current_ids = get_draft_image_file_ids(agent)
        if new_file_id not in current_ids:
            if len(current_ids) >= MAX_DRAFT_IMAGES:
                return {"ok": False, "error": f"Максимум {MAX_DRAFT_IMAGES} фото на пост"}
            current_ids.append(new_file_id)
            set_draft_image_file_ids(agent, current_ids)
        await db.commit()
        return {"ok": True, "mode": "image_added", "file_ids": current_ids}

    elif action == "remove_image":
        # Remove an image from draft
        rm_file_id = str(body.get("file_id", "")).strip()
        if not rm_file_id:
            return {"ok": False, "error": "file_id не указан"}
        current_ids = get_draft_image_file_ids(agent)
        current_ids = [fid for fid in current_ids if fid != rm_file_id]
        set_draft_image_file_ids(agent, current_ids)
        await db.commit()
        return {"ok": True, "mode": "image_removed", "file_ids": current_ids}

    return {"ok": False, "error": f"Неизвестное действие: {action}"}


@router.post("/threads/{thread_id}/verify-channel")
async def verify_poster_channel(
    thread_id: UUID,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis_client: redis.Redis = Depends(get_redis),
):
    """Verify bot + user admin status and save poster_channel_id if OK.
    
    Body: {"channel_id": "@channel or numeric ID or link"} (required on first setup)
    Falls back to stored poster_channel_id when body.channel_id is absent.
    """
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    from app.services.agent.max_probe import probe_max_chat, resolve_channel_link
    from app.services.bot import MaxBotService

    cfg = dict(agent.config or {})
    # Accept channel from request body (new setup / channel change), fallback to stored value
    channel_id_raw = str(body.get("channel_id") or cfg.get("poster_channel_id") or "").strip()
    if not channel_id_raw:
        return {"ok": False, "bot_is_admin": False, "error": "Канал не указан в настройках"}

    bot = MaxBotService()

    # Try to parse as numeric ID first
    raw_clean = channel_id_raw.lstrip("@").replace("https://max.ru/", "").strip("/")
    try:
        channel_id: int | None = int(raw_clean)
    except ValueError:
        channel_id = None

    if not channel_id:
        # String link — resolve via API
        try:
            resolved = await resolve_channel_link(bot, channel_id_raw)
            if not resolved.get("ok") or not resolved.get("chat_id"):
                return {"ok": False, "bot_is_admin": False, "error": f"Не удалось найти канал «{channel_id_raw}». Проверьте ID или ссылку."}
            channel_id = int(resolved["chat_id"])
        except Exception as exc:
            return {"ok": False, "bot_is_admin": False, "error": str(exc)[:200]}

    try:
        probe = await probe_max_chat(bot, channel_id)
        if not probe.get("ok"):
            return {
                "ok": False,
                "bot_is_admin": False,
                "user_is_admin": None,
                "chat_name": "",
                "channel_id": channel_id,
                "error": probe.get("error", "Бот не является администратором канала"),
            }

        # Require user to have a MAX account — poster agent sends via MAX bot
        from app.services.agent.max_group import check_user_is_group_admin
        user_max_id = user.max_user_id
        if not user_max_id:
            return {
                "ok": False,
                "bot_is_admin": True,
                "user_is_admin": None,
                "chat_name": probe.get("title") or probe.get("chat_name", ""),
                "channel_id": channel_id,
                "error": "Для использования агента постинга необходимо привязать аккаунт MAX в профиле.",
            }

        # Check that the requesting USER is also an admin of the channel.
        # This prevents users from publishing to channels they don't control.
        user_is_admin: bool | None = None
        user_is_admin = await check_user_is_group_admin(bot, channel_id, int(user_max_id))
        # Fail closed: if we can't confirm the user is admin, block activation.
        # None means the API check couldn't run (bot lacks member-read permissions
        # or user not found in channel). Either way, we cannot verify ownership.
        if user_is_admin is not True:
            err_msg = (
                "Вы не являетесь администратором этого канала. Публикация доступна только администраторам."
                if user_is_admin is False else
                "Не удалось проверить права администратора в канале. Убедитесь, что вы являетесь администратором, и попробуйте снова."
            )
            return {
                "ok": False,
                "bot_is_admin": True,
                "user_is_admin": user_is_admin,
                "chat_name": probe.get("title") or probe.get("chat_name", ""),
                "channel_id": channel_id,
                "error": err_msg,
            }

        # Both bot and user are admins — save and activate
        cfg["poster_channel_id"] = str(channel_id)
        cfg.pop("is_new", None)  # канал подтверждён = первое действие, тред появляется в истории
        from sqlalchemy.orm.attributes import flag_modified as _flag_mod
        agent.config = cfg
        _flag_mod(agent, "config")
        from app.models.agent import AgentStatus
        if agent.status in (AgentStatus.DRAFT.value, "draft"):
            agent.status = AgentStatus.ACTIVE.value
        await db.commit()

        return {
            "ok": True,
            "bot_is_admin": True,
            "user_is_admin": user_is_admin,  # True or None (couldn't check)
            "chat_name": probe.get("title") or probe.get("chat_name", ""),
            "channel_id": channel_id,
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "bot_is_admin": False, "user_is_admin": None, "error": str(exc)[:200]}


# ─────────────────────────────────────────────────────────────────────────────
# Secretary agent endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/threads/{thread_id}/verify-group")
async def verify_secretary_group(
    thread_id: UUID,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    redis_client: redis.Redis = Depends(get_redis),
):
    """Verify bot presence in MAX group and save max_chat_id for secretary agent.

    Body: {"group_id": "@group or numeric ID or link"} (required on first setup)
    Falls back to stored max_chat_id when body.group_id is absent.
    Also recompiles secretary rules when support_instructions is set.
    """
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    from app.services.agent.max_probe import probe_max_chat, resolve_channel_link
    from app.services.bot import MaxBotService

    cfg = dict(agent.config or {})
    group_id_raw = str(
        body.get("group_id") or body.get("channel_id") or
        cfg.get("max_chat_id") or agent.max_chat_id or ""
    ).strip()
    if not group_id_raw:
        return {"ok": False, "error": "ID группы не указан"}

    bot = MaxBotService()
    raw_clean = group_id_raw.lstrip("@").replace("https://max.ru/", "").strip("/")
    try:
        group_id: int | None = int(raw_clean)
    except ValueError:
        group_id = None

    if not group_id:
        try:
            resolved = await resolve_channel_link(bot, group_id_raw)
            if not resolved.get("ok") or not resolved.get("chat_id"):
                return {"ok": False, "error": f"Не удалось найти группу «{group_id_raw}». Проверьте ID или ссылку."}
            group_id = int(resolved["chat_id"])
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    try:
        probe = await probe_max_chat(bot, group_id, send_test=False)
        if not probe.get("ok"):
            return {
                "ok": False,
                "bot_is_admin": False,
                "chat_name": "",
                "group_id": group_id,
                "error": probe.get("error", "Бот не может подключиться к группе. Убедитесь что бот добавлен в группу."),
            }

        # Save group to config and agent.max_chat_id
        cfg["max_chat_id"] = group_id
        cfg["task_mode"] = "secretary"
        cfg["role"] = "dm_assistant"
        cfg["scope"] = "group"
        cfg["interaction_mode"] = "support"
        cfg["delivery_mode"] = "group"
        from sqlalchemy.orm.attributes import flag_modified as _fm_sec
        from app.models.agent import AgentRole as _AR
        agent.config = cfg
        agent.max_chat_id = group_id
        agent.role = _AR.DM_ASSISTANT.value  # нужна колонка role для поиска в group_interactive
        _fm_sec(agent, "config")

        # Activate agent if still in DRAFT/COLLECTING
        from app.models.agent import AgentStatus as _AS
        if agent.status in (_AS.DRAFT.value, "draft", _AS.COLLECTING.value, "collecting"):
            agent.status = _AS.ACTIVE.value

        # Recompile rules if categories are configured
        support_instructions = str(cfg.get("support_instructions") or "").strip()
        compiled_ok = False
        if support_instructions:
            try:
                from app.services.providers.factory import resolve_agent_providers
                from app.services.agent.secretary_compiler import compile_secretary_rules
                llm, _, _, _, _ = await resolve_agent_providers(db, redis_client, user=user)
                rules = await compile_secretary_rules(llm, support_instructions)
                if rules:
                    cfg["compiled_rules"] = rules
                    agent.config = cfg
                    _fm_sec(agent, "config")
                    compiled_ok = True
            except Exception as _ce:
                logger.warning("verify-group: rule compile failed: %s", _ce)

        cfg.pop("is_new", None)  # подключение группы = первое действие, тред появляется в истории
        agent.config = cfg
        _fm_sec(agent, "config")
        await db.commit()
        return {
            "ok": True,
            "bot_is_admin": bool(probe.get("bot_is_admin")),
            "chat_name": probe.get("title") or probe.get("chat_name", ""),
            "group_id": group_id,
            "compiled_rules": compiled_ok,
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "bot_is_admin": False, "error": str(exc)[:200]}


@router.get("/threads/{thread_id}/records")
async def get_secretary_records(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = 50,
    offset: int = 0,
):
    """Return expense records for secretary agent (paginated, newest first)."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        return {"records": [], "total": 0}

    cfg = dict(agent.config or {})
    raw = cfg.get("agent_records") or {}
    records: list[dict] = []
    if isinstance(raw, dict):
        records = list(raw.get("records") or [])
    # Newest first
    records = list(reversed(records))
    total = len(records)
    page = records[offset: offset + limit]
    return {"records": page, "total": total}


@router.delete("/threads/{thread_id}/records/{record_id}")
async def delete_secretary_record(
    thread_id: UUID,
    record_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Delete a single expense record by _id."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    from app.services.agent.agent_records import delete_record_by_id
    from sqlalchemy.orm.attributes import flag_modified as _fm_del
    deleted = delete_record_by_id(agent, "records", record_id)
    _fm_del(agent, "config")
    await db.commit()
    return {"ok": deleted, "record_id": record_id}


@router.post("/threads/{thread_id}/records/clear")
async def clear_secretary_records(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Clear all expense records for secretary agent."""
    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.thread_type == ThreadType.AGENT,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тред не найден")
    agent = await get_agent_for_thread(db, thread.id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Агент не найден")

    from sqlalchemy.orm.attributes import flag_modified as _fm_clr
    cfg = dict(agent.config or {})
    cfg["agent_records"] = {"records": []}
    agent.config = cfg
    _fm_clr(agent, "config")
    await db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Reminder management endpoints
# ─────────────────────────────────────────────────────────────────────────────

_WEEKDAY_RU = {
    "mon": "понедельник",
    "tue": "вторник",
    "wed": "среда",
    "thu": "четверг",
    "fri": "пятница",
    "sat": "суббота",
    "sun": "воскресенье",
}


def _build_schedule_text(body: dict) -> str:
    """Convert form fields to a schedule_text string parseable by parse_reminder_schedule."""
    stype = str(body.get("schedule_type") or "one_time")
    time_str = str(body.get("time") or "09:00").strip() or "09:00"

    if stype == "daily":
        return f"каждый день в {time_str}"

    if stype == "weekly":
        day_key = str(body.get("weekday") or "mon")
        day_ru = _WEEKDAY_RU.get(day_key, day_key)
        return f"каждый {day_ru} в {time_str}"

    if stype == "monthly":
        day_of_month = int(body.get("day_of_month") or 1)
        return f"раз в месяц каждое {day_of_month} число в {time_str}"

    if stype == "quarterly":
        return f"раз в квартал в {time_str}"

    if stype == "yearly":
        return f"раз в год в {time_str}"

    if stype == "interval":
        value = int(body.get("interval_value") or 30)
        unit = body.get("interval_unit") or "minutes"
        if unit == "hours":
            return f"через {value} часов"
        return f"через {value} минут"

    # one_time — need date in YYYY-MM-DD format for parse_reminder_schedule
    date_str = str(body.get("date") or "").strip()
    if date_str:
        # Convert DD.MM.YYYY or DD/MM/YYYY → YYYY-MM-DD
        import re as _re
        m = _re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", date_str)
        if m:
            dd, mm, yyyy = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
            date_str = f"{yyyy}-{mm}-{dd}"
        return f"{date_str} {time_str}"
    return f"сегодня в {time_str}"


def _recurrence_label(recurrence: str | None) -> str:
    if not recurrence:
        return "Разово"
    if recurrence == "daily":
        return "Ежедневно"
    if recurrence == "hourly":
        return "Каждый час"
    if recurrence == "quarterly":
        return "Раз в квартал"
    if recurrence == "yearly":
        return "Раз в год"
    if recurrence.startswith("weekly:"):
        wd_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        try:
            idx = int(recurrence.split(":")[1])
            return f"Еженедельно ({wd_names[idx]})"
        except (IndexError, ValueError):
            return "Еженедельно"
    if recurrence.startswith("monthly:"):
        try:
            day = recurrence.split(":")[1]
            return f"Ежемесячно ({day}-е)"
        except IndexError:
            return "Ежемесячно"
    return recurrence


async def _get_hub_and_reminder_agents(
    db: AsyncSession,
    thread_id: UUID,
    user: "User",
):
    """Returns (hub_agent, list_of_sub_reminder_agents)."""
    from app.models.agent import AgentInstance

    result = await db.execute(
        select(Thread).where(
            Thread.id == thread_id,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Тред не найден")

    hub_agent = await get_agent_for_thread(db, thread.id)
    if not hub_agent:
        raise HTTPException(status_code=404, detail="Агент не найден")

    sub_result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.user_id == user.id,
            AgentInstance.config["parent_hub_id"].astext == str(hub_agent.id),
            AgentInstance.status != "cancelled",
        ).order_by(AgentInstance.created_at.asc())
    )
    sub_agents = list(sub_result.scalars().all())
    return hub_agent, sub_agents


def _agent_to_reminder_out(agent: "AgentInstance") -> dict:
    cfg = dict(agent.config or {})
    return {
        "id": str(agent.id),
        "thread_id": str(agent.thread_id),
        "name": cfg.get("reminder_name", ""),
        "text": cfg.get("reminder_message", ""),
        "schedule_text": cfg.get("schedule_text", ""),
        "schedule_type": cfg.get("schedule_type", "one_time"),
        "time": cfg.get("schedule_time", ""),
        "weekday": cfg.get("schedule_weekday", ""),
        "day_of_month": cfg.get("schedule_day_of_month"),
        "date": cfg.get("schedule_date", ""),
        "interval_value": cfg.get("schedule_interval_value"),
        "interval_unit": cfg.get("schedule_interval_unit", "minutes"),
        "delivery_mode": cfg.get("delivery_mode", "dm"),
        "max_chat_id": agent.max_chat_id,
        "timezone": cfg.get("timezone", "Europe/Moscow"),
        "enabled": agent.status == "active",
        "status": agent.status,
        "next_run_at": cfg.get("next_run_at"),
        "recurrence_label": _recurrence_label(cfg.get("recurrence_stored")),
    }


_REMINDER_MAX_PER_USER = 20   # hard cap on active reminder sub-agents per hub
_REMINDER_MIN_INTERVAL_MIN = 5  # minimum interval schedule in minutes
_REMINDER_TEXT_MAX_LEN = 4000   # MAX API message limit


async def _check_group_reminder_ownership(
    bot: "MaxBotService", user: "User", max_chat_id: int
) -> None:
    """Raise HTTPException if the user is not a verified admin of the target group."""
    if not user.max_user_id:
        raise HTTPException(
            status_code=422,
            detail="Для отправки напоминаний в группу необходимо привязать аккаунт MAX в профиле.",
        )
    from app.services.agent.max_group import check_user_is_group_admin
    is_admin = await check_user_is_group_admin(bot, max_chat_id, int(user.max_user_id))
    if is_admin is not True:
        msg = (
            "Вы не являетесь администратором этой группы."
            if is_admin is False else
            "Не удалось проверить права в группе. Убедитесь, что вы администратор, и попробуйте снова."
        )
        raise HTTPException(status_code=403, detail=msg)


def _parse_max_chat_id(raw) -> int | None:
    """Parse max_chat_id safely; raise 422 on invalid input."""
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="max_chat_id должен быть числом")


def _validate_reminder_timezone(tz: str) -> str:
    import zoneinfo
    try:
        zoneinfo.ZoneInfo(tz)
        return tz
    except Exception:
        return "Europe/Moscow"


def _enforce_min_interval(body: dict) -> None:
    """Raise 422 if schedule interval is below the minimum."""
    if str(body.get("schedule_type") or "") == "interval":
        unit = str(body.get("interval_unit") or "minutes")
        value = int(body.get("interval_value") or 1)
        if unit == "minutes" and value < _REMINDER_MIN_INTERVAL_MIN:
            raise HTTPException(
                status_code=422,
                detail=f"Минимальный интервал — {_REMINDER_MIN_INTERVAL_MIN} минут.",
            )


@router.get("/threads/{thread_id}/reminders")
async def list_reminders(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """List all reminder sub-agents linked to a hub reminder thread."""
    from app.services.agent.access import require_agent_eligible
    require_agent_eligible(user)
    hub_agent, sub_agents = await _get_hub_and_reminder_agents(db, thread_id, user)
    return {"reminders": [_agent_to_reminder_out(a) for a in sub_agents]}


@router.post("/threads/{thread_id}/reminders")
async def create_reminder(
    thread_id: UUID,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Create a new reminder sub-agent linked to this hub thread."""
    from app.models.agent import AgentInstance, AgentStatus
    from app.services.agent.reminders import activate_agent_direct
    from app.services.agent.schedule import parse_reminder_schedule
    from app.services.agent.access import require_agent_eligible
    from app.services.bot import MaxBotService

    require_agent_eligible(user)
    hub_agent, existing = await _get_hub_and_reminder_agents(db, thread_id, user)

    # Cap: max reminders per hub
    active_count = sum(1 for a in existing if a.status not in ("cancelled", "paused"))
    if active_count >= _REMINDER_MAX_PER_USER:
        raise HTTPException(
            status_code=422,
            detail=f"Достигнут лимит: максимум {_REMINDER_MAX_PER_USER} напоминаний.",
        )

    # Enforce minimum interval
    _enforce_min_interval(body)

    # Validate timezone
    timezone = _validate_reminder_timezone(str(body.get("timezone") or "Europe/Moscow"))
    delivery_mode = str(body.get("delivery_mode") or "dm")
    role = "group_reminder" if delivery_mode == "group" else "personal_reminder"
    max_chat_id = _parse_max_chat_id(body.get("max_chat_id"))

    # Security: verify user is admin of the target group
    if delivery_mode == "group":
        if not max_chat_id:
            raise HTTPException(status_code=422, detail="Укажите ID группы для группового напоминания.")
        bot = MaxBotService()
        await _check_group_reminder_ownership(bot, user, max_chat_id)

    schedule_text = _build_schedule_text(body)
    try:
        run_at, recurrence = parse_reminder_schedule(schedule_text, tz_name=timezone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Не удалось разобрать расписание: {exc}")

    from app.services.thread_factory import create_thread, next_agent_seq
    seq = await next_agent_seq(db, user.id)
    sub_thread = await create_thread(
        db,
        user_id=user.id,
        title=f"Напоминание {seq}",
        thread_type=ThreadType.AGENT,
        agent_seq=seq,
    )

    max_uid = int(user.max_user_id) if user.max_user_id else 0
    reminder_text = str(body.get("text") or "Напоминание")[:_REMINDER_TEXT_MAX_LEN]
    reminder_name = str(body.get("name") or "").strip()[:60]
    sub_cfg: dict = {
        "template": "reminder",
        "is_sub_reminder": True,
        "parent_hub_id": str(hub_agent.id),
        "reminder_name": reminder_name,
        "reminder_message": reminder_text,
        "schedule_text": schedule_text,
        "schedule_type": str(body.get("schedule_type") or "one_time"),
        "schedule_time": str(body.get("time") or ""),
        "schedule_weekday": str(body.get("weekday") or ""),
        "schedule_day_of_month": body.get("day_of_month"),
        "schedule_date": str(body.get("date") or ""),
        "schedule_interval_value": body.get("interval_value"),
        "schedule_interval_unit": str(body.get("interval_unit") or "minutes"),
        "timezone": timezone,
        "delivery_mode": delivery_mode,
        "content_pipeline": "static",
        "recurrence_stored": recurrence,
    }

    sub_agent = AgentInstance(
        thread_id=sub_thread.id,
        user_id=user.id,
        max_user_id=max_uid,
        status=AgentStatus.DRAFT.value,
        role=role,
        config=sub_cfg,
        max_chat_id=max_chat_id,
    )
    db.add(sub_agent)
    await db.flush()

    try:
        await activate_agent_direct(db, sub_agent)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Ошибка активации: {exc}")

    # Первое напоминание — снимаем флаг «новый» с hub-агента, тред появляется в истории
    hub_cfg = dict(hub_agent.config or {})
    if hub_cfg.pop("is_new", None) is not None:
        from sqlalchemy.orm.attributes import flag_modified as _flag_modified
        hub_agent.config = hub_cfg
        _flag_modified(hub_agent, "config")

    await db.commit()
    await db.refresh(sub_agent)

    return _agent_to_reminder_out(sub_agent)


@router.patch("/threads/{thread_id}/reminders/{reminder_agent_id}")
async def update_reminder(
    thread_id: UUID,
    reminder_agent_id: UUID,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Update a reminder sub-agent (reschedule, change text, or toggle enabled)."""
    from app.models.agent import AgentStatus
    from app.services.agent.reminders import activate_agent_direct, cancel_reminders_for_agent
    from app.services.agent.schedule import parse_reminder_schedule
    from app.services.agent.access import require_agent_eligible
    from app.services.bot import MaxBotService

    require_agent_eligible(user)
    _enforce_min_interval(body)

    hub_agent, sub_agents = await _get_hub_and_reminder_agents(db, thread_id, user)
    sub_agent = next((a for a in sub_agents if a.id == reminder_agent_id), None)
    if not sub_agent:
        raise HTTPException(status_code=404, detail="Напоминание не найдено")

    cfg = dict(sub_agent.config or {})

    if "name" in body:
        cfg["reminder_name"] = str(body.get("name") or "").strip()[:60]
    if "text" in body:
        cfg["reminder_message"] = str(body["text"])[:_REMINDER_TEXT_MAX_LEN]
    if "timezone" in body:
        cfg["timezone"] = _validate_reminder_timezone(str(body["timezone"]))

    delivery_mode = str(body.get("delivery_mode") or cfg.get("delivery_mode") or "dm")
    cfg["delivery_mode"] = delivery_mode
    sub_agent.role = "group_reminder" if delivery_mode == "group" else "personal_reminder"

    if "max_chat_id" in body:
        new_chat_id = _parse_max_chat_id(body["max_chat_id"])
        # Verify user is admin if switching to/staying in group mode
        if delivery_mode == "group" and new_chat_id:
            bot = MaxBotService()
            await _check_group_reminder_ownership(bot, user, new_chat_id)
        sub_agent.max_chat_id = new_chat_id
    elif delivery_mode == "group" and sub_agent.max_chat_id:
        # Delivery mode unchanged but still group — re-verify on mode change
        pass

    # Always refresh max_user_id from current user (handles MAX re-link)
    sub_agent.max_user_id = int(user.max_user_id) if user.max_user_id else 0

    schedule_fields = {"schedule_type", "time", "weekday", "day_of_month", "date", "interval_value", "interval_unit"}
    needs_reschedule = bool(schedule_fields & set(body.keys()))

    if needs_reschedule:
        for k in schedule_fields:
            if k in body:
                cfg[f"schedule_{k}"] = body[k]
        if "schedule_type" in body:
            cfg["schedule_type"] = str(body["schedule_type"])

        merged = {**cfg}
        merged["schedule_type"] = cfg.get("schedule_type", "one_time")
        merged["time"] = cfg.get("schedule_time", "09:00")
        merged["weekday"] = cfg.get("schedule_weekday", "mon")
        merged["day_of_month"] = cfg.get("schedule_day_of_month", 1)
        merged["date"] = cfg.get("schedule_date", "")
        merged["interval_value"] = cfg.get("schedule_interval_value", 30)
        merged["interval_unit"] = cfg.get("schedule_interval_unit", "minutes")

        schedule_text = _build_schedule_text(merged)
        timezone = cfg.get("timezone", "Europe/Moscow")
        try:
            run_at, recurrence = parse_reminder_schedule(schedule_text, tz_name=timezone)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Не удалось разобрать расписание: {exc}")
        cfg["schedule_text"] = schedule_text
        cfg["recurrence_stored"] = recurrence

    from sqlalchemy.orm.attributes import flag_modified as _fm
    sub_agent.config = cfg
    _fm(sub_agent, "config")
    await db.flush()

    try:
        if "enabled" in body:
            if body["enabled"]:
                await activate_agent_direct(db, sub_agent)
            else:
                await cancel_reminders_for_agent(db, sub_agent.id)
                sub_agent.status = AgentStatus.PAUSED.value
                await db.flush()
        elif needs_reschedule:
            await activate_agent_direct(db, sub_agent)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Ошибка активации: {exc}")

    await db.commit()
    await db.refresh(sub_agent)
    return _agent_to_reminder_out(sub_agent)


@router.delete("/threads/{thread_id}/reminders/{reminder_agent_id}")
async def delete_reminder(
    thread_id: UUID,
    reminder_agent_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Cancel and soft-delete a reminder sub-agent."""
    from app.models.agent import AgentStatus
    from app.services.agent.reminders import cancel_reminders_for_agent
    from datetime import datetime, timezone as _tz

    hub_agent, sub_agents = await _get_hub_and_reminder_agents(db, thread_id, user)
    sub_agent = next((a for a in sub_agents if a.id == reminder_agent_id), None)
    if not sub_agent:
        raise HTTPException(status_code=404, detail="Напоминание не найдено")

    await cancel_reminders_for_agent(db, sub_agent.id)

    # Удаляем sub-thread напоминания
    sub_thread_result = await db.execute(
        select(Thread).where(Thread.id == sub_agent.thread_id)
    )
    sub_thread = sub_thread_result.scalar_one_or_none()
    if sub_thread:
        sub_thread.deleted_at = datetime.now(_tz.utc)

    # Hard delete самого агента — восстановление не нужно
    await db.delete(sub_agent)
    await db.commit()
    return {"ok": True}
