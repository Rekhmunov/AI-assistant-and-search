"""Обработчики callback-кнопок агента «Постинг»."""
from __future__ import annotations

import logging
import uuid

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentStatus
from app.services.bot import MaxBotService
from app.services.agent.poster_executor import (
    clear_pending_draft,
    edit_draft_message,
    generate_post,
    generate_poster_image,
    get_pending_draft,
    get_poster_channel_id,
    get_approval_destination,
    mark_draft_message_done,
    publish_to_channel,
    save_pending_draft,
    save_post_to_history,
    send_draft_for_approval,
    set_awaiting_edit,
    update_post_status,
    _pick_next_topic,
)

logger = logging.getLogger(__name__)


async def _notify_owner(bot: MaxBotService, agent: AgentInstance, text: str) -> None:
    """Send a status notification to the correct destination (group or DM)."""
    dest_chat_id, dest_user_id = get_approval_destination(agent)
    try:
        if dest_chat_id:
            await bot.send_message(None, text, chat_id=dest_chat_id, notify=False)
        elif dest_user_id:
            await bot.send_message(dest_user_id, text)
    except Exception as exc:
        logger.warning("poster _notify_owner failed: %s", exc)


async def handle_poster_callback(
    db: AsyncSession,
    redis_client: aioredis.Redis,
    *,
    callback_id: str,
    payload: str,
    clicker_user_id: int | None,
    bot: MaxBotService | None = None,
) -> bool:
    if not payload.startswith("poster:"):
        return False

    bot = bot or MaxBotService()
    parts = payload.split(":")
    if len(parts) < 4:
        return False

    _, action, agent_id_str, post_id = parts[0], parts[1], parts[2], parts[3]

    try:
        agent_uuid = uuid.UUID(agent_id_str)
    except ValueError:
        return False

    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.id == agent_uuid,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        await bot.answer_callback(callback_id, "Агент не найден.")
        return True

    # Security: only the agent owner can act on draft buttons.
    # Fail closed: reject if clicker unknown OR agent has no MAX ID.
    if clicker_user_id is None or not agent.max_user_id:
        await bot.answer_callback(callback_id, "Не удалось подтвердить личность. Используйте веб-интерфейс.")
        return True
    if int(clicker_user_id) != int(agent.max_user_id):
        await bot.answer_callback(callback_id, "Это действие доступно только владельцу агента.")
        return True

    draft = get_pending_draft(agent)
    if not draft or draft.get("post_id") != post_id:
        await bot.answer_callback(callback_id, "Черновик устарел или уже обработан.")
        return True

    channel_id = get_poster_channel_id(agent)
    draft_message_id = draft.get("draft_message_id")

    if action == "approve":
        # Atomic idempotency: fail if another approve is already in progress
        if draft.get("publishing"):
            await bot.answer_callback(callback_id, "Пост уже публикуется, подождите.")
            return True
        # Mark as publishing before any async work
        from app.services.agent.poster_executor import save_pending_draft as _spd_cb
        _spd_cb(agent, post_id=post_id, topic=draft.get("topic", ""),
                text=draft.get("text", ""), draft_message_id=draft_message_id)
        _cb_cfg = dict(agent.config or {})
        _cb_pdr = _cb_cfg.get("poster_pending_draft", {})
        _cb_pdr["publishing"] = True
        _cb_cfg["poster_pending_draft"] = _cb_pdr
        from sqlalchemy.orm.attributes import flag_modified as _fm_cb
        agent.config = _cb_cfg
        _fm_cb(agent, "config")
        await db.flush()
        # Answer immediately so button doesn't freeze
        await bot.answer_callback(callback_id, "⏳ Публикуем пост…")
        await _handle_approve(db, redis_client, agent, bot,
                              draft=draft, channel_id=channel_id,
                              draft_message_id=draft_message_id)

    elif action == "reject":
        await bot.answer_callback(callback_id, "Пост отклонён.")
        await _handle_reject(db, agent, bot,
                             draft=draft, draft_message_id=draft_message_id)

    elif action == "regen":
        # Rate-limit DM regen the same as web regen
        from app.core.limiter import RateLimiter
        from app.models.user import User as _User
        from sqlalchemy import select as _sel
        _user_res = await db.execute(_sel(_User).where(_User.id == agent.user_id))
        _cb_user = _user_res.scalar_one_or_none()
        if _cb_user:
            _cb_limiter = RateLimiter(redis_client)
            _cb_allowed, _, _ = await _cb_limiter.check_search_limit(
                str(_cb_user.id), _cb_user.plan, user=_cb_user
            )
            if not _cb_allowed:
                await bot.answer_callback(callback_id, "Достигнут дневной лимит запросов.")
                return True
        await bot.answer_callback(callback_id, "🔄 Генерирую новый вариант…")
        await _handle_regen(db, redis_client, agent, bot,
                            draft=draft, draft_message_id=draft_message_id)

    elif action == "edit":
        set_awaiting_edit(agent, True)
        await bot.answer_callback(callback_id, "✏️ Отправьте исправленный текст.")
        await _notify_owner(bot, agent, "✏️ Отправьте исправленный текст поста следующим сообщением.")

    await db.commit()
    return True


async def _handle_approve(
    db: AsyncSession,
    redis_client,
    agent: AgentInstance,
    bot: MaxBotService,
    *,
    draft: dict,
    channel_id: int | None,
    draft_message_id: str | None,
) -> None:
    if not channel_id:
        await _notify_owner(bot, agent, "❌ Канал не настроен. Укажите канал в настройках агента.")
        return

    text = draft.get("text", "")
    post_id = draft.get("post_id", "")
    topic = draft.get("topic", "")

    # Generate image if ai mode
    image_bytes = await generate_poster_image(agent, topic, text, db=db, redis_client=redis_client)

    ok = await publish_to_channel(bot, channel_id=channel_id, text=text, image_bytes=image_bytes)
    if ok:
        update_post_status(agent, post_id, "published")
        clear_pending_draft(agent)
        # Update DM message to show published status
        if draft_message_id:
            await mark_draft_message_done(bot, draft_message_id=draft_message_id,
                                          status_text=f"✅ Пост «{topic[:60]}» опубликован в канале.")
        else:
            await _notify_owner(bot, agent, f"✅ Пост «{topic[:60]}» опубликован в канале.")
    else:
        await _notify_owner(bot, agent, "❌ Ошибка публикации. Проверьте права бота в канале.")


async def _handle_reject(
    db: AsyncSession,
    agent: AgentInstance,
    bot: MaxBotService,
    *,
    draft: dict,
    draft_message_id: str | None,
) -> None:
    post_id = draft.get("post_id", "")
    topic = draft.get("topic", "")
    update_post_status(agent, post_id, "rejected")
    clear_pending_draft(agent)
    # Update DM message to show rejected status
    if draft_message_id:
        await mark_draft_message_done(bot, draft_message_id=draft_message_id,
                                      status_text=f"❌ Пост «{topic[:60]}» отклонён.")
    else:
        await _notify_owner(bot, agent, f"❌ Пост «{topic[:60]}» отклонён.")


async def _handle_regen(
    db: AsyncSession,
    redis_client,
    agent: AgentInstance,
    bot: MaxBotService,
    *,
    draft: dict,
    draft_message_id: str | None,
) -> None:
    from app.services.providers.factory import resolve_agent_providers
    from app.services.agent.poster_executor import _topic_text

    # draft["topic"] is always a plain string; _pick_next_topic returns {text, search}
    topic_raw = draft.get("topic")  # str or None
    if topic_raw:
        topic_obj = topic_raw  # pass string directly (search flag not restored on regen)
        topic = topic_raw
    else:
        topic_obj = _pick_next_topic(agent)  # dict {text, search}
        topic = _topic_text(topic_obj)

    old_post_id = draft.get("post_id", "")
    update_post_status(agent, old_post_id, "rejected")
    clear_pending_draft(agent)

    try:
        llm, _, _, _, _ = await resolve_agent_providers(db, redis_client)
        new_text = await generate_post(agent, topic_obj, llm, db=db, redis_client=redis_client)
        new_id = str(uuid.uuid4())

        save_post_to_history(agent, post_id=new_id, topic=topic, text=new_text, status="draft")
        save_pending_draft(agent, post_id=new_id, topic=topic, text=new_text)

        # Generate new image (always uses string topic)
        new_image_bytes = await generate_poster_image(agent, topic, new_text, db=db, redis_client=redis_client)

        if draft_message_id:
            # Edit the existing DM message with new draft
            await edit_draft_message(
                bot, agent,
                draft_message_id=draft_message_id,
                post_id=new_id, topic=topic, text=new_text,
                image_bytes=new_image_bytes,
            )
            save_pending_draft(agent, post_id=new_id, topic=topic,
                               text=new_text, draft_message_id=draft_message_id)
        else:
            # Send new message
            msg_id = await send_draft_for_approval(
                agent, db, bot,
                post_id=new_id, topic=topic, text=new_text,
                image_bytes=new_image_bytes,
            )
            save_pending_draft(agent, post_id=new_id, topic=topic,
                               text=new_text, draft_message_id=msg_id)

    except Exception as exc:
        logger.exception("Poster regen failed: %s", exc)
        await _notify_owner(bot, agent, "❌ Не удалось перегенерировать пост. Попробуйте позже.")


async def handle_poster_edit_input(
    db: AsyncSession,
    agent: AgentInstance,
    bot: MaxBotService,
    *,
    text: str,
    approval_chat_id: int,
) -> bool:
    draft = get_pending_draft(agent)
    if not draft or not draft.get("awaiting_edit"):
        return False

    set_awaiting_edit(agent, False)
    post_id = draft.get("post_id", str(uuid.uuid4()))
    topic = draft.get("topic", "—")
    old_msg_id = draft.get("draft_message_id")
    save_pending_draft(agent, post_id=post_id, topic=topic, text=text)

    if old_msg_id:
        # Edit the existing DM message (no image needed — user edited text)
        await edit_draft_message(bot, agent, draft_message_id=old_msg_id,
                                 post_id=post_id, topic=topic, text=text)
        save_pending_draft(agent, post_id=post_id, topic=topic,
                           text=text, draft_message_id=old_msg_id)
    else:
        msg_id = await send_draft_for_approval(
            agent, db, bot,
            post_id=post_id, topic=topic, text=text,
        )
        save_pending_draft(agent, post_id=post_id, topic=topic,
                           text=text, draft_message_id=msg_id)
    return True
