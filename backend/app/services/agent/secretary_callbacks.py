"""
Обработка inline-кнопок агента «Учет затрат».

Форматы payload:
  secretary:delete:{agent_id}:{record_id}        — удалить запись
  secretary:clarify:{agent_id}:{category_name}   — выбрать категорию для уточнения
  secretary:clarify_cancel:{agent_id}            — отменить ввод затраты
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

    if action == "clarify":
        return await _handle_clarify(db, bot, agent, callback_id, parts, clicker_user_id)

    if action == "clarify_cancel":
        return await _handle_clarify_cancel(db, bot, agent, callback_id, clicker_user_id)

    await bot.answer_callback(callback_id)
    return False


async def _handle_delete(
    db: AsyncSession,
    bot: MaxBotService,
    agent: AgentInstance,
    callback_id: str,
    parts: list[str],
) -> bool:
    """Удаляет запись по _id, убирает кнопку из сообщения и подтверждает через answer_callback."""
    record_id = parts[3] if len(parts) > 3 else ""
    if not record_id:
        await bot.answer_callback(callback_id, "Ошибка: ID записи не найден")
        return False

    from app.services.agent.agent_records import delete_record_by_id, query_records

    # Находим запись до удаления, чтобы получить message_id и текст подтверждения
    all_records = query_records(agent, "records", limit=5000)
    target = next((r for r in all_records if r.get("_id") == record_id), None)
    confirm_msg_id: str | None = target.get("_mid") if target else None
    confirm_text: str = ""
    if target:
        category = str(target.get("category") or "")
        amount = target.get("amount", "")
        amt_str = str(int(amount)) if isinstance(amount, float) and amount == int(amount) else str(amount)
        confirm_text = f"✅ Записано в категорию: {category} — {amt_str}"

    deleted = delete_record_by_id(agent, "records", record_id)

    if deleted:
        await bot.answer_callback(callback_id, "✅ Запись удалена")
        # Редактируем исходное сообщение — убираем кнопку, добавляем пометку об удалении
        if confirm_msg_id:
            await bot.edit_message(
                confirm_msg_id,
                text=f"~~{confirm_text}~~ _(удалено)_",
                remove_keyboard=True,
            )
        logger.info("secretary_callback: deleted record _id=%s agent=%s mid=%s", record_id, agent.id, confirm_msg_id)
    else:
        await bot.answer_callback(callback_id, "Запись уже была удалена")
        # Убираем кнопку если она ещё есть
        if confirm_msg_id:
            await bot.edit_message(confirm_msg_id, text=f"{confirm_text} _(удалено)_", remove_keyboard=True)
        logger.info("secretary_callback: record _id=%s not found agent=%s", record_id, agent.id)

    return True


async def _handle_clarify(
    db: AsyncSession,
    bot: MaxBotService,
    agent: AgentInstance,
    callback_id: str,
    parts: list[str],
    clicker_user_id: int | None,
) -> bool:
    """Пользователь нажал кнопку с категорией — записываем затрату."""
    from app.services.agent.secretary_executor import _get_pending, _set_pending, _send_clarify_buttons
    from app.services.agent.agent_records import store_record
    from sqlalchemy.orm.attributes import flag_modified as _fm

    # Формат: secretary:clarify:{agent_id}:{category_name}
    # или:    secretary:clarify:{agent_id}:{entity_name}:{option_variant}
    if len(parts) < 4:
        await bot.answer_callback(callback_id, "Ошибка: категория не указана")
        return False
    if len(parts) >= 5:
        # require_clarification: category = "entity_name (вариант)"
        entity_name = parts[3]
        option_variant = ":".join(parts[4:])
        category_name = f"{entity_name} ({option_variant})"
    else:
        category_name = parts[3]
    if not category_name:
        await bot.answer_callback(callback_id, "Ошибка: категория не указана")
        return False

    pending = _get_pending(agent)
    if not pending or pending.get("type") != "clarify_entity":
        await bot.answer_callback(callback_id, "Уточнение уже не актуально")
        return False

    queue: list[dict] = pending.get("queue", [])
    if not queue:
        _set_pending(agent, None)
        await bot.answer_callback(callback_id)
        return False

    first = queue[0]
    amount = first.get("amount")
    token = first.get("token", "")

    store_record(agent, "records", {
        "category": category_name,
        "amount": amount,
        "note": token,
    })
    _fm(agent, "config")

    amt_str = str(int(amount)) if amount and amount == int(amount) else str(amount or "")
    confirm_text = f"✅ Записано: {category_name} — {amt_str}"

    pending_chat_id = pending.get("chat_id")
    remaining = queue[1:]
    if remaining:
        # Сохраняем chat_id при переходе к следующему элементу очереди
        _set_pending(agent, {"type": "clarify_entity", "queue": remaining, "chat_id": pending_chat_id})
        await db.commit()
        await bot.answer_callback(callback_id, "✅ Записано")
        await bot.send_message(None, confirm_text, chat_id=pending_chat_id)
        rules = (agent.config or {}).get("compiled_rules", {})
        entities = rules.get("entities", [])
        next_amt = remaining[0].get("amount")
        next_amt_str = str(int(next_amt)) if next_amt and next_amt == int(next_amt) else str(next_amt or "")
        from app.services.agent.secretary_executor import _send_clarify_item_buttons as _scib
        await _scib(bot, agent, entities, remaining[0], next_amt_str, chat_id=pending_chat_id)
    else:
        _set_pending(agent, None)
        await db.commit()
        await bot.answer_callback(callback_id, "✅ Записано")
        # Отправляем подтверждение в чат
        await bot.send_message(None, confirm_text, chat_id=pending_chat_id)

    logger.info("secretary_callback: clarify saved category=%s amount=%s agent=%s", category_name, amount, agent.id)
    return True


async def _handle_clarify_cancel(
    db: AsyncSession,
    bot: MaxBotService,
    agent: AgentInstance,
    callback_id: str,
    clicker_user_id: int | None,
) -> bool:
    """Пользователь нажал Отмена — пропускаем первый элемент очереди."""
    from app.services.agent.secretary_executor import _get_pending, _set_pending, _send_clarify_buttons
    from sqlalchemy.orm.attributes import flag_modified as _fm

    pending = _get_pending(agent)
    if not pending or pending.get("type") != "clarify_entity":
        await bot.answer_callback(callback_id)
        return False

    queue: list[dict] = pending.get("queue", [])
    remaining = queue[1:] if queue else []

    pending_chat_id = pending.get("chat_id")
    if remaining:
        # Сохраняем chat_id при переходе к следующему элементу
        _set_pending(agent, {"type": "clarify_entity", "queue": remaining, "chat_id": pending_chat_id})
        _fm(agent, "config")
        await db.commit()
        await bot.answer_callback(callback_id, "Отменено")
        rules = (agent.config or {}).get("compiled_rules", {})
        entities = rules.get("entities", [])
        next_amt = remaining[0].get("amount")
        next_amt_str = str(int(next_amt)) if next_amt and next_amt == int(next_amt) else str(next_amt or "")
        from app.services.agent.secretary_executor import _send_clarify_item_buttons as _scib2
        await _scib2(bot, agent, entities, remaining[0], next_amt_str, chat_id=pending_chat_id)
    else:
        _set_pending(agent, None)
        _fm(agent, "config")
        await db.commit()
        await bot.answer_callback(callback_id, "Отменено")

    logger.info("secretary_callback: clarify_cancel agent=%s", agent.id)
    return True
