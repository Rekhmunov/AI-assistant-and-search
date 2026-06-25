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
        # poster_* and support_instructions are allowed; validate timezone
        if key == "poster_timezone":
            import zoneinfo
            try:
                zoneinfo.ZoneInfo(str(value))
            except Exception:
                continue  # skip invalid timezone
        if key.startswith("poster_") or key in ("support_instructions",):
            cfg[key] = value
    agent.config = cfg
    await db.commit()
    return {"ok": True, "config": {k: v for k, v in cfg.items() if k.startswith("poster_")}}


@router.get("/threads/{thread_id}/post-history")
async def get_poster_history(
    thread_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Return post history for the poster agent."""
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
        return {"items": []}

    from app.services.agent.poster_executor import get_post_history
    history = get_post_history(agent)
    return {"items": list(reversed(history[-20:]))}  # latest first


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

        topic = _pick_next_topic(agent)
        llm, _, _, _, _ = await resolve_agent_providers(db, redis_client)
        post_text = await generate_post(agent, topic, llm)
        post_id = str(_uuid.uuid4())

        save_post_to_history(agent, post_id=post_id, topic=topic, text=post_text, status="draft")

        approval_mode = get_approval_mode(agent)
        channel_id = get_poster_channel_id(agent)
        bot = MaxBotService()

        # Generate image if ai mode configured
        image_bytes = await generate_poster_image(agent, topic, post_text, db=db, redis_client=redis_client)

        if approval_mode == "auto" and channel_id:
            # Auto-publish: publish directly
            ok = await publish_to_channel(bot, channel_id=channel_id, text=post_text, image_bytes=image_bytes)
            if ok:
                update_post_status(agent, post_id, "published")
                await db.commit()
                return {"ok": True, "mode": "published", "topic": topic, "post_text": post_text}
            return {"ok": False, "error": "Не удалось опубликовать в канал. Проверьте права бота."}
        else:
            # Manual draft: save image as temp file for preview, return URL to frontend
            image_url: str | None = None
            image_file_ids_list: list[str] = []
            if image_bytes:
                try:
                    # Save for later use at approval time
                    from app.services.image_gen_service import persist_generated_image
                    fid, _ = await persist_generated_image(db, user, image_bytes, title=topic, ttl_hours=24)
                    image_file_ids_list = [str(fid)]
                    import base64 as _b64
                    from app.services.image_bytes import detect_image_mime as _detect_mime
                    _mime = _detect_mime(image_bytes) or "image/jpeg"
                    image_url = f"data:{_mime};base64,{_b64.b64encode(image_bytes).decode('ascii')}"
                except Exception as img_exc:
                    logger.warning("poster draft image save failed: %s", img_exc)

            save_pending_draft(agent, post_id=post_id, topic=topic, text=post_text,
                               image_file_ids=image_file_ids_list if image_file_ids_list else [])

            await db.commit()
            return {
                "ok": True,
                "mode": "web_draft",
                "topic": topic,
                "post_id": post_id,
                "post_text": post_text,
                "image_url": image_url,  # None if no ai image or save failed
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

    draft = get_pending_draft(agent)
    if not draft or draft.get("post_id") != post_id:
        return {"ok": False, "error": "Черновик устарел или уже обработан"}

    bot = MaxBotService()
    draft_message_id = draft.get("draft_message_id")  # for DM sync

    if action == "approve":
        channel_id = get_poster_channel_id(agent)
        if not channel_id:
            return {"ok": False, "error": "Канал не настроен"}
        draft_text = draft.get("text", "")
        draft_topic = draft.get("topic", "")

        # Load all stored images for this draft
        image_file_ids = get_draft_image_file_ids(agent)
        logger.warning("POSTER_APPROVE image_file_ids=%s channel=%s", image_file_ids, channel_id)

        images_bytes_list: list[bytes] = []
        for fid in image_file_ids:
            try:
                from uuid import UUID as _UUID2
                _uf_res = await db.execute(select(_UF).where(_UF.id == _UUID2(fid)))
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
        logger.info("POSTER_APPROVE publish ok=%s image=%s", ok, "yes" if image_bytes else "no")
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
        new_text = str(body.get("text", "")).strip()
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
        from app.services.providers.factory import resolve_agent_providers
        from app.services.image_gen_service import persist_generated_image
        import uuid as _uuid
        topic = draft.get("topic", _pick_next_topic(agent))
        update_post_status(agent, post_id, "rejected")
        clear_pending_draft(agent)
        try:
            llm, _, _, _, _ = await resolve_agent_providers(db, redis_client)
            new_text = await generate_post(agent, topic, llm)
            new_id = str(_uuid.uuid4())
            save_post_to_history(agent, post_id=new_id, topic=topic, text=new_text, status="draft")
            save_pending_draft(agent, post_id=new_id, topic=topic, text=new_text)

            # Also regenerate image
            image_url: str | None = None
            image_bytes_regen = await generate_poster_image(agent, topic, new_text, db=db, redis_client=redis_client)
            if image_bytes_regen:
                try:
                    fid, _ = await persist_generated_image(db, user, image_bytes_regen, title=topic, ttl_hours=24)
                    # Store image_file_id in draft for approval reuse
                    cfg = dict(agent.config or {})
                    draft_data = cfg.get("poster_pending_draft", {})
                    draft_data["image_file_id"] = str(fid)
                    cfg["poster_pending_draft"] = draft_data
                    agent.config = cfg
                    # Return base64 data URL for instant preview (no auth needed)
                    import base64 as _b64
                    from app.services.image_bytes import detect_image_mime as _detect_mime
                    _mime = _detect_mime(image_bytes_regen) or "image/jpeg"
                    image_url = f"data:{_mime};base64,{_b64.b64encode(image_bytes_regen).decode('ascii')}"
                except Exception as img_exc:
                    logger.warning("poster regen image save failed: %s", img_exc)

            # Edit DM message with new draft
            if draft_message_id and image_bytes_regen:
                try:
                    await edit_draft_message(
                        bot, agent, draft_message_id=draft_message_id,
                        post_id=new_id, topic=topic, text=new_text,
                        image_bytes=image_bytes_regen,
                    )
                    save_pending_draft(agent, post_id=new_id, topic=topic,
                                       text=new_text, draft_message_id=draft_message_id)
                except Exception as _dme:
                    logger.warning("regen DM edit failed: %s", _dme)
            elif draft_message_id:
                try:
                    await edit_draft_message(
                        bot, agent, draft_message_id=draft_message_id,
                        post_id=new_id, topic=topic, text=new_text,
                    )
                    save_pending_draft(agent, post_id=new_id, topic=topic,
                                       text=new_text, draft_message_id=draft_message_id)
                except Exception as _dme:
                    logger.warning("regen DM edit (no img) failed: %s", _dme)

            await db.commit()
            return {"ok": True, "mode": "web_draft", "post_id": new_id, "post_text": new_text,
                    "topic": topic, "image_url": image_url}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    elif action == "regen_image":
        # Regenerate AI image only (keep current text)
        topic = draft.get("topic", "")
        text = draft.get("text", "")
        try:
            new_image_bytes = await generate_poster_image(agent, topic, text, db=db, redis_client=redis_client)
            if not new_image_bytes:
                return {"ok": False, "error": "Не удалось сгенерировать изображение"}
            from app.services.image_gen_service import persist_generated_image, public_file_content_url
            import uuid as _uuid
            fid, _ = await persist_generated_image(db, user, new_image_bytes, title=topic, ttl_hours=24)
            # Replace all existing images with the new AI one
            set_draft_image_file_ids(agent, [str(fid)])
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
        if not new_file_id:
            return {"ok": False, "error": "file_id не указан"}
        try:
            _uf_r = await db.execute(select(_UF).where(_UF.id == _UUID3(new_file_id), _UF.user_id == user.id))
            _uf = _uf_r.scalar_one_or_none()
            if not _uf:
                return {"ok": False, "error": "Файл не найден"}
        except Exception:
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

    from app.services.agent.max_probe import probe_max_chat, resolve_channel_link
    from app.services.bot import MaxBotService

    cfg = dict(agent.config or {})
    channel_id_raw = str(cfg.get("poster_channel_id") or "").strip()
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
        if probe.get("ok"):
            # Save the resolved numeric channel_id back to config
            cfg["poster_channel_id"] = str(channel_id)
            agent.config = cfg
            # Activate agent so Celery picks it up for scheduled posting
            from app.models.agent import AgentStatus
            if agent.status in (AgentStatus.DRAFT.value, "draft"):
                agent.status = AgentStatus.ACTIVE.value
            await db.commit()

        return {
            "ok": probe.get("ok", False),
            "bot_is_admin": probe.get("bot_is_admin", False),
            "chat_name": probe.get("title") or probe.get("chat_name", ""),
            "channel_id": channel_id,
            "error": probe.get("error", "") if not probe.get("ok") else "",
        }
    except Exception as exc:
        return {"ok": False, "bot_is_admin": False, "error": str(exc)[:200]}
