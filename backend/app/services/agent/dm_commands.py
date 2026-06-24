"""Интерактивный бот в личном чате MAX: команды, поддержка, vision."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.models.user import User
from app.services.agent.interaction import (
    agent_scope,
    interaction_mode,
    should_handle_dm,
)
from app.services.agent.max_compliance import dm_command_allowed
from app.services.agent.max_media import message_has_images
from app.services.agent.profile import agent_config, normalize_dm_command
from app.services.agent.reminders import effective_max_user_id
from app.services.agent.support_reply import build_interactive_reply
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


def parse_dm_command(text: str) -> tuple[str | None, str]:
    """Возвращает (команда, аргументы). /news arg → ('news', 'arg')."""
    raw = (text or "").strip()
    if not raw:
        return None, ""
    parts = raw.split(maxsplit=1)
    head = parts[0].lower()
    if head.startswith("/"):
        head = head[1:]
    args = parts[1].strip() if len(parts) > 1 else ""
    return head or None, args


async def _active_dm_agents(db: AsyncSession, *, max_user_id: int) -> list[AgentInstance]:
    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.max_user_id == max_user_id,
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.role == AgentRole.DM_ASSISTANT.value,
        )
    )
    return list(result.scalars().all())


async def find_dm_agent_for_interaction(
    db: AsyncSession,
    *,
    max_user_id: int,
    text: str,
    has_images: bool,
) -> AgentInstance | None:
    agents = await _active_dm_agents(db, max_user_id=max_user_id)
    if not agents:
        return None

    command, _args = parse_dm_command(text)
    matches: list[AgentInstance] = []
    for agent in agents:
        cfg = agent_config(agent)
        if agent_scope(cfg) not in {"dm", "both"}:
            continue
        cmd = normalize_dm_command(cfg.get("dm_command"))
        if should_handle_dm(agent, text=text, command=cmd, has_images=has_images):
            matches.append(agent)

    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    configured = [a for a in matches if normalize_dm_command(agent_config(a).get("dm_command")) == command]
    if len(configured) == 1:
        return configured[0]
    logger.warning("Ambiguous DM agent for user %s, picking first", max_user_id)
    return matches[0]


async def find_dm_agent_for_command(
    db: AsyncSession,
    *,
    max_user_id: int,
    command: str | None,
) -> AgentInstance | None:
    if not command:
        return None
    agents = await _active_dm_agents(db, max_user_id=max_user_id)
    matches: list[AgentInstance] = []
    for agent in agents:
        cfg = agent_config(agent)
        cmd = normalize_dm_command(cfg.get("dm_command"))
        if cmd and cmd == command:
            matches.append(agent)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.warning("Ambiguous dm command %s for user %s", command, max_user_id)
        return matches[0]
    return None


async def list_dm_commands_for_user(db: AsyncSession, *, max_user_id: int) -> list[str]:
    cmds: list[str] = []
    for agent in await _active_dm_agents(db, max_user_id=max_user_id):
        cfg = agent_config(agent)
        cmd = normalize_dm_command(cfg.get("dm_command"))
        if cmd:
            cmds.append(cmd)
    return sorted(set(cmds))


async def handle_dm_message(
    db: AsyncSession,
    redis_client,
    *,
    max_user_id: int,
    text: str,
    payload: dict[str, Any] | None = None,
    message_id_value: str | None = None,
    bot: MaxBotService | None = None,
) -> bool:
    """
    Обрабатывает личное сообщение боту.
    Возвращает True, если ответ отправлен (не показывать welcome-поведение).
    """
    bot = bot or MaxBotService()
    low = (text or "").strip().lower()
    has_images = message_has_images(payload or {})

    if low in {"help", "помощь", "команды", "commands", "/help"}:
        cmds = await list_dm_commands_for_user(db, max_user_id=max_user_id)
        agents = await _active_dm_agents(db, max_user_id=max_user_id)
        if not cmds and not agents:
            return False
        lines: list[str] = []
        if cmds:
            lines.append("Команды:\n" + "\n".join(f"• /{c}" for c in cmds))
        for agent in agents:
            mode = interaction_mode(agent_config(agent))
            if mode in {"support", "both"}:
                lines.append("Можно писать обычным текстом — бот ответит как поддержка.")
                if has_images:
                    lines.append("Можно отправить фото с подписью «переведи текст с картинки».")
                break
        await bot.send_message(max_user_id, "\n\n".join(lines) if lines else "Агенты активны.")
        return True

    # Poster agent: check if awaiting text edit in DM context
    from sqlalchemy import select as _select
    _poster_result = await db.execute(
        _select(AgentInstance).where(
            AgentInstance.max_user_id == max_user_id,
            AgentInstance.status == AgentStatus.ACTIVE.value,
        )
    )
    for _poster_agent in _poster_result.scalars().all():
        _cfg = dict(_poster_agent.config or {})
        if _cfg.get("template") != "poster":
            continue
        _draft = _cfg.get("poster_pending_draft")
        if _draft and _draft.get("awaiting_edit") and text:
            try:
                from app.services.agent.poster_callbacks import handle_poster_edit_input
                from app.services.agent.poster_executor import get_approval_destination, _pick_next_topic
                dest_chat, dest_user = get_approval_destination(_poster_agent)
                # For DM context, approval goes back to user DM
                _handled = await handle_poster_edit_input(
                    db, _poster_agent, bot,
                    text=text,
                    approval_chat_id=dest_chat or 0,
                )
                if _handled:
                    await db.commit()
                    return True
            except Exception as _exc:
                logger.warning("poster dm edit-input failed: %s", _exc)

    # Личный ассистент обрабатывается до всех других агентов
    from app.services.agent.assistant_bot_handler import handle_assistant_dm
    assistant_handled = await handle_assistant_dm(
        db,
        redis_client,
        max_user_id=max_user_id,
        text=text,
        payload=payload or {},
        message_id_value=message_id_value,
        bot=bot,
    )
    if assistant_handled:
        return True

    if not await dm_command_allowed(max_user_id):
        return True

    agent = await find_dm_agent_for_interaction(
        db,
        max_user_id=max_user_id,
        text=text,
        has_images=has_images,
    )
    if not agent:
        return False

    user_result = await db.execute(select(User).where(User.max_user_id == max_user_id).limit(1))
    user = user_result.scalar_one_or_none()
    if not user:
        await bot.send_message(max_user_id, "Привяжите MAX в профиле Glosix, чтобы использовать агента.")
        return True

    if not effective_max_user_id(agent):
        agent.max_user_id = max_user_id

    cfg = agent_config(agent)
    command = normalize_dm_command(cfg.get("dm_command"))
    mode = interaction_mode(cfg)

    try:
        reply_text, attachments = await build_interactive_reply(
            db,
            redis_client,
            user,
            agent,
            text=text,
            payload=payload,
            message_id_value=message_id_value,
            bot=bot,
            force_command=mode == "command" and bool(command),
            chat_id=max_user_id,
        )
        if not (reply_text or "").strip() and not attachments:
            return True
        result = await bot.send_message(
            max_user_id,
            reply_text,
            attachments=attachments or None,
        )
        if not result.ok:
            await bot.send_message(max_user_id, "Не удалось ответить. Попробуйте позже.")
    except Exception as exc:
        logger.exception("DM interactive failed agent=%s: %s", agent.id, exc)
        await bot.send_message(max_user_id, "Ошибка при обработке сообщения.")
    return True
