"""
Обработка inline-кнопок агента «Учет затрат».

Форматы payload:
  secretary:delete:{agent_id}:{record_id}   — удалить запись
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


async def handle_secretary_callback(
    db: AsyncSession,
    *,
    callback_id: str,
    payload: str,
    clicker_user_id: int | None = None,
) -> bool:
    """
    Разбирает payload кнопки и выполняет нужное действие.
    Возвращает True если событие обработано.
    clicker_user_id — MAX user_id нажавшего кнопку (из callback.user.user_id).
    """
    bot = MaxBotService()
    parts = payload.split(":")
    if len(parts) < 3 or parts[0] != "secretary":
        await bot.answer_callback(callback_id)
        return False

    action = parts[1]
    try:
        agent_id = UUID(parts[2])
    except (ValueError, IndexError):
        logger.warning("secretary_callback: invalid agent_id in payload=%s", payload)
        await bot.answer_callback(callback_id, "Ошибка: агент не найден")
        return False

    result = await db.execute(
        select(AgentInstance).where(AgentInstance.id == agent_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        logger.warning("secretary_callback: agent %s not found", agent_id)
        await bot.answer_callback(callback_id, "Ошибка: агент не найден")
        return False

    # Только владелец агента может управлять записями
    if clicker_user_id is not None and agent.max_user_id is not None:
        if int(clicker_user_id) != int(agent.max_user_id):
            await bot.answer_callback(callback_id, "Только владелец агента может управлять записями")
            logger.warning(
                "secretary_callback: access denied clicker=%s owner=%s agent=%s",
                clicker_user_id, agent.max_user_id, agent_id,
            )
            return False

    if action == "delete":
        return await _handle_delete(db, bot, agent, callback_id, parts)

    await bot.answer_callback(callback_id)
    return False


async def _handle_delete(
    db: AsyncSession,
    bot: MaxBotService,
    agent: AgentInstance,
    callback_id: str,
    parts: list[str],
) -> bool:
    """Удаляет запись по _id и подтверждает через answer_callback."""
    record_id = parts[3] if len(parts) > 3 else ""
    if not record_id:
        await bot.answer_callback(callback_id, "Ошибка: ID записи не найден")
        return False

    from app.services.agent.agent_records import delete_record_by_id
    deleted = delete_record_by_id(agent, "records", record_id)

    if deleted:
        await bot.answer_callback(callback_id, "✅ Запись удалена")
        logger.info("secretary_callback: deleted record _id=%s agent=%s", record_id, agent.id)
    else:
        await bot.answer_callback(callback_id, "Запись уже была удалена")
        logger.info("secretary_callback: record _id=%s not found agent=%s", record_id, agent.id)

    return True


