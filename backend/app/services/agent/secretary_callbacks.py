"""
Обработка inline-кнопок агента «Учет затрат».

Форматы payload:
  secretary:delete:{agent_id}:{record_id}   — удалить запись
  secretary:report:{agent_id}:{period}      — сформировать отчёт за период
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentStatus
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


async def handle_secretary_callback(
    db: AsyncSession,
    *,
    callback_id: str,
    payload: str,
) -> bool:
    """
    Разбирает payload кнопки и выполняет нужное действие.
    Возвращает True если событие обработано.
    """
    bot = MaxBotService()
    parts = payload.split(":")
    if len(parts) < 3 or parts[0] != "secretary":
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

    if action == "delete":
        return await _handle_delete(db, bot, agent, callback_id, parts)

    if action == "report":
        return await _handle_report(db, bot, agent, callback_id, parts)

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


async def _handle_report(
    db: AsyncSession,
    bot: MaxBotService,
    agent: AgentInstance,
    callback_id: str,
    parts: list[str],
) -> bool:
    """Формирует Excel-отчёт за выбранный период и отправляет в группу."""
    period_code = parts[3] if len(parts) > 3 else ""
    chat_id = agent.max_chat_id
    if not chat_id:
        await bot.answer_callback(callback_id, "Ошибка: группа не привязана")
        return False

    today = datetime.now(timezone.utc)

    if period_code == "today":
        start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end = today.replace(hour=23, minute=59, second=59)
        label = today.strftime("%d.%m.%Y")
    elif period_code == "yesterday":
        yesterday = today - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59)
        label = yesterday.strftime("%d.%m.%Y")
    elif period_code == "week":
        start = (today - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = today.replace(hour=23, minute=59, second=59)
        label = f"{start.strftime('%d.%m')} – {today.strftime('%d.%m.%Y')}"
    elif period_code == "month":
        start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = today.replace(hour=23, minute=59, second=59)
        label = today.strftime("%B %Y")
    elif period_code == "custom":
        await bot.answer_callback(callback_id)
        await bot.send_message(
            None,
            "Введите дату или диапазон в чат, например:\n"
            "• 14.06.2026\n"
            "• с 01.06 по 14.06",
            chat_id=int(chat_id),
            notify=False,
        )
        return True
    else:
        await bot.answer_callback(callback_id, "Неизвестный период")
        return False

    from app.services.agent.agent_records import query_records
    records = query_records(agent, "records", limit=5000)

    filtered = []
    for r in records:
        at_str = r.get("at", "")
        try:
            at = datetime.fromisoformat(at_str)
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            if start <= at <= end:
                filtered.append(r)
        except Exception:
            pass

    await bot.answer_callback(callback_id, f"Формирую отчёт за {label}...")

    if not filtered:
        await bot.send_message(
            None,
            f"За период {label} записей не найдено.",
            chat_id=int(chat_id),
            notify=False,
        )
        return True

    title = f"Отчёт за {label}"
    columns = ["Категория", "Затрата", "Примечание"]
    field_keys = ["category", "amount", "note"]

    try:
        import re as _re
        from app.services.xlsx_builder import build_xlsx_bytes
        from app.services.doc_gen_schema import DocumentStructure, DocTable

        rows = [[str(r.get(k, "")) for k in field_keys] for r in filtered]
        structure = DocumentStructure(
            title=title,
            tables=[DocTable(caption=title, headers=columns, rows=rows)],
        )
        xlsx_bytes = build_xlsx_bytes(structure)
        safe_title = _re.sub(r"[^\w\-]", "_", title)[:40]
        filename = f"{safe_title}.xlsx"

        token = await bot.upload_media(xlsx_bytes, filename, "file")
        if token:
            attachment = {"type": "file", "payload": {"token": token}}
            await bot.send_message(
                None,
                f"{title} — {len(filtered)} записей:",
                attachments=[attachment],
                chat_id=int(chat_id),
                notify=False,
            )
        else:
            await bot.send_message(
                None,
                f"⚠️ Не удалось загрузить файл отчёта.",
                chat_id=int(chat_id),
                notify=False,
            )
    except Exception as exc:
        logger.exception("secretary report generation failed agent=%s: %s", agent.id, exc)
        await bot.send_message(
            None,
            f"⚠️ Ошибка при формировании отчёта: {exc!s:.100}",
            chat_id=int(chat_id),
            notify=False,
        )

    return True
