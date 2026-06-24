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
    generate_post,
    get_pending_draft,
    get_poster_channel_id,
    get_approval_destination,
    publish_to_channel,
    save_pending_draft,
    save_post_to_history,
    send_draft_for_approval,
    set_awaiting_edit,
    update_post_status,
    _get_cfg,
    _pick_next_topic,
)

logger = logging.getLogger(__name__)


async def _notify_owner(
    bot: MaxBotService,
    agent: AgentInstance,
    text: str,
) -> None:
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
            AgentInstance.status == AgentStatus.ACTIVE.value,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        await bot.answer_callback(callback_id, "Агент не найден.")
        return True

    draft = get_pending_draft(agent)
    if not draft or draft.get("post_id") != post_id:
        await bot.answer_callback(callback_id, "Черновик устарел или уже обработан.")
        return True

    channel_id = get_poster_channel_id(agent)

    if action == "approve":
        await _handle_approve(db, agent, bot, callback_id, draft=draft, channel_id=channel_id)
    elif action == "reject":
        await _handle_reject(db, agent, bot, callback_id, draft=draft)
    elif action == "regen":
        await _handle_regen(db, redis_client, agent, bot, callback_id, draft=draft)
    elif action == "edit":
        await _handle_edit(agent, bot, callback_id, draft=draft)

    await db.commit()
    return True


async def _handle_approve(
    db: AsyncSession,
    agent: AgentInstance,
    bot: MaxBotService,
    callback_id: str,
    *,
    draft: dict,
    channel_id: int | None,
) -> None:
    if not channel_id:
        await bot.answer_callback(callback_id, "Канал не настроен. Укажите канал в настройках агента.")
        return

    text = draft.get("text", "")
    post_id = draft.get("post_id", "")
    topic = draft.get("topic", "")

    ok = await publish_to_channel(bot, channel_id=channel_id, text=text)
    if ok:
        update_post_status(agent, post_id, "published")
        clear_pending_draft(agent)
        await bot.answer_callback(callback_id, "✅ Пост опубликован!")
        await _notify_owner(bot, agent, f"✅ Пост «{topic[:60]}» опубликован в канале.")
    else:
        await bot.answer_callback(callback_id, "❌ Ошибка публикации. Проверьте права бота в канале.")


async def _handle_reject(
    db: AsyncSession,
    agent: AgentInstance,
    bot: MaxBotService,
    callback_id: str,
    *,
    draft: dict,
) -> None:
    post_id = draft.get("post_id", "")
    topic = draft.get("topic", "")
    update_post_status(agent, post_id, "rejected")
    clear_pending_draft(agent)
    await bot.answer_callback(callback_id, "Пост отклонён.")
    await _notify_owner(bot, agent, f"❌ Пост «{topic[:60]}» отклонён.")


async def _handle_regen(
    db: AsyncSession,
    redis_client: aioredis.Redis,
    agent: AgentInstance,
    bot: MaxBotService,
    callback_id: str,
    *,
    draft: dict,
) -> None:
    from app.services.providers.factory import resolve_agent_providers

    await bot.answer_callback(callback_id, "🔄 Генерирую новый вариант…")

    topic = draft.get("topic", _pick_next_topic(agent))
    old_post_id = draft.get("post_id", "")
    update_post_status(agent, old_post_id, "rejected")
    clear_pending_draft(agent)

    try:
        llm, _, _, _, _ = await resolve_agent_providers(db, redis_client)
        new_text = await generate_post(agent, topic, llm)
        new_post_id = str(uuid.uuid4())

        save_post_to_history(agent, post_id=new_post_id, topic=topic, text=new_text, status="draft")
        save_pending_draft(agent, post_id=new_post_id, topic=topic, text=new_text)

        msg_id = await send_draft_for_approval(
            agent, db, bot,
            post_id=new_post_id, topic=topic, text=new_text,
        )
        save_pending_draft(agent, post_id=new_post_id, topic=topic, text=new_text, draft_message_id=msg_id)

    except Exception as exc:
        logger.exception("Poster regen failed: %s", exc)
        await _notify_owner(bot, agent, "❌ Не удалось перегенерировать пост. Попробуйте позже.")


async def _handle_edit(
    agent: AgentInstance,
    bot: MaxBotService,
    callback_id: str,
    *,
    draft: dict,
) -> None:
    set_awaiting_edit(agent, True)
    await bot.answer_callback(callback_id, "✏️ Отправьте исправленный текст поста.")
    await _notify_owner(bot, agent, "✏️ Отправьте исправленный текст поста следующим сообщением.")


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
    save_pending_draft(agent, post_id=post_id, topic=topic, text=text)

    msg_id = await send_draft_for_approval(
        agent, db, bot,
        post_id=post_id, topic=topic, text=text,
    )
    save_pending_draft(agent, post_id=post_id, topic=topic, text=text, draft_message_id=msg_id)
    return True
