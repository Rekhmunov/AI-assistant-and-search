"""Интерактивные ответы агента в групповых чатах MAX."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.models.user import User
from app.services.agent.interaction import interaction_mode, should_handle_group
from app.services.agent.max_compliance import group_reply_allowed
from app.services.agent.max_media import message_has_images
from app.services.agent.profile import agent_config, normalize_dm_command
from app.services.agent.support_reply import build_interactive_reply
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


async def _owner_user(db: AsyncSession, agent: AgentInstance) -> User | None:
    result = await db.execute(select(User).where(User.id == agent.user_id).limit(1))
    return result.scalar_one_or_none()


async def handle_group_interactive(
    db: AsyncSession,
    redis_client,
    *,
    chat_id: int,
    text: str,
    author: str,
    payload: dict[str, Any],
    message_id_value: str | None = None,
    bot: MaxBotService | None = None,
) -> bool:
    """Отвечает в группе от имени dm_assistant с scope group/both. Возвращает True если ответ отправлен."""
    if author == "bot":
        return False

    bot = bot or MaxBotService()

    # ── Быстрый путь: compiled_rules executor (без LLM) ──────────────────────
    # Ищем активного секретаря с compiled_rules для данного chat_id
    from sqlalchemy import select as _select
    _res = await db.execute(
        _select(AgentInstance).where(
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.role == AgentRole.DM_ASSISTANT.value,
            AgentInstance.max_chat_id == chat_id,
        )
    )
    _quick_agents = list(_res.scalars().all())
    for _agent in _quick_agents:
        _cfg = _agent.config or {}
        if _cfg.get("template") == "secretary" and isinstance(_cfg.get("compiled_rules"), dict):
            # Секретарь с compiled_rules работает ТОЛЬКО по коду — LLM не вызывается
            try:
                from app.services.agent.secretary_executor import execute_secretary_message, ExecutorResult
                exec_result = await execute_secretary_message(
                    db, _agent, bot, chat_id, text, author
                )
                if exec_result is not None:
                    if exec_result.file_instruction:
                        from app.services.agent.document_delivery import build_document_delivery_content
                        from app.models.user import User
                        _owner = await db.execute(_select(User).where(User.id == _agent.user_id).limit(1))
                        _owner_user = _owner.scalar_one_or_none()
                        if _owner_user:
                            content = await build_document_delivery_content(
                                db, redis_client, _owner_user,
                                exec_result.file_instruction,
                                output_format=exec_result.file_format,
                                bot=bot,
                            )
                            await bot.send_message(
                                None,
                                exec_result.text or "Файл:",
                                attachments=content.attachments or None,
                                chat_id=chat_id,
                            )
                    elif exec_result.text:
                        await bot.send_message(None, exec_result.text, chat_id=chat_id)
                # Если executor вернул None — сообщение не распознано.
                # Для секретаря с compiled_rules LLM НЕ вызывается.
                # Просто игнорируем (агент молчит на нераспознанные сообщения).
                await db.commit()
                return True  # Всегда возвращаем True — LLM не нужен
            except Exception as exc:
                logger.exception("Secretary executor error agent=%s: %s", _agent.id, exc)
                return True  # Даже при ошибке не вызываем LLM
    # ─────────────────────────────────────────────────────────────────────────
    has_images = message_has_images(payload)

    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.role == AgentRole.DM_ASSISTANT.value,
            AgentInstance.max_chat_id == chat_id,
        )
    )
    agents = list(result.scalars().all())
    logger.info(
        "GROUP_INTERACTIVE chat_id=%s found_agents=%s text_preview=%s",
        chat_id, len(agents), (text or "")[:50],
    )
    if not agents:
        return False

    for agent in agents:
        cfg = agent_config(agent)
        command = normalize_dm_command(cfg.get("dm_command"))
        if not should_handle_group(
            agent,
            text=text,
            command=command,
            has_images=has_images,
            chat_id=chat_id,
        ):
            continue

        owner = await _owner_user(db, agent)
        if not owner:
            continue

        if not await group_reply_allowed(chat_id):
            return True

        try:
            reply_text, attachments = await build_interactive_reply(
                db,
                redis_client,
                owner,
                agent,
                text=text,
                payload=payload,
                message_id_value=message_id_value,
                bot=bot,
                force_command=interaction_mode(cfg) == "command" and bool(command),
                chat_id=chat_id,
                author=author,
            )
            if not (reply_text or "").strip() and not attachments:
                return True
            send_result = await bot.send_message(
                None,
                reply_text,
                attachments=attachments or None,
                chat_id=chat_id,
            )
            if not send_result.ok:
                logger.warning(
                    "Group interactive reply failed chat=%s agent=%s err=%s",
                    chat_id,
                    agent.id,
                    send_result.error,
                )
            return True
        except Exception as exc:
            logger.exception("Group interactive failed agent=%s: %s", agent.id, exc)
            return True

    return False
