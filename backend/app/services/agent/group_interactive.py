"""Интерактивные ответы агента в групповых чатах MAX."""

from __future__ import annotations

import logging
import re
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

        # ── Отмена ожидающей записи ───────────────────────────────────────────
        if _cfg.get("template") == "secretary" and text.strip().lower() in {"отмена", "отменить", "cancel"}:
            from app.services.agent.agent_spec import load_agent_spec, save_agent_spec
            _spec = load_agent_spec(_agent)
            has_pending = any(f.lower().startswith("pending_entry") for f in _spec.facts)
            if has_pending:
                _spec.facts = [f for f in _spec.facts if not f.lower().startswith("pending_entry")]
                save_agent_spec(_agent, _spec)
                await bot.send_message(None, "❌ Отменено. Запись не сохранена.", chat_id=chat_id, notify=False)
                await db.commit()
                return True

        # ── Ожидание ввода даты для отчёта (после нажатия «Ввести дату вручную») ──
        if _cfg.get("template") == "secretary" and _cfg.get("secretary_pending_report"):
            try:
                handled = await _handle_pending_date_report(db, _agent, bot, chat_id, text)
                if handled:
                    await db.commit()
                    return True
            except Exception as exc:
                logger.exception("Secretary pending date report failed agent=%s: %s", _agent.id, exc)

        if _cfg.get("template") == "secretary" and isinstance(_cfg.get("compiled_rules"), dict):
            # Секретарь с compiled_rules работает ТОЛЬКО по коду — LLM не вызывается
            try:
                from app.services.agent.secretary_executor import execute_secretary_message, ExecutorResult
                exec_result = await execute_secretary_message(
                    db, _agent, bot, chat_id, text, author
                )
                if exec_result is not None:
                    if exec_result.xlsx_data:
                        # Генерируем Excel напрямую из данных — без LLM
                        try:
                            from app.services.xlsx_builder import build_report_xlsx_bytes
                            xd = exec_result.xlsx_data
                            title = xd.get("title", "Отчёт")
                            columns = xd.get("columns", ["Категория", "Затрата", "Примечание"])
                            records_data = xd.get("records", [])
                            field_keys = ["category", "amount", "note"]
                            rows = [[str(r.get(k, "")) for k in field_keys] for r in records_data]
                            xlsx_bytes = build_report_xlsx_bytes(columns, rows, sheet_name=title[:31])
                            safe_title = re.sub(r"[^\w\-]", "_", title)[:40]
                            filename = f"{safe_title}.xlsx"
                            token = await bot.upload_media(xlsx_bytes, filename, "file")
                            attachment = {"type": "file", "payload": {"token": token}} if token else None
                            await bot.send_message(
                                None,
                                exec_result.text or title,
                                attachments=[attachment] if attachment else None,
                                chat_id=chat_id,
                            )
                        except Exception as exc:
                            logger.warning("Secretary xlsx generation failed: %s", exc)
                            await bot.send_message(None, f"{exec_result.text}\n\n⚠️ Не удалось сформировать файл.", chat_id=chat_id)
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


async def _handle_pending_date_report(
    db,
    agent: AgentInstance,
    bot: MaxBotService,
    chat_id: int,
    text: str,
) -> bool:
    """
    Обрабатывает ввод даты/диапазона после нажатия «Ввести дату вручную».
    Если дата распознана — генерирует Excel-отчёт и сбрасывает флаг.
    Возвращает True если сообщение обработано (даже если дата не распознана).
    """
    from datetime import datetime, timezone
    from app.services.agent.secretary_executor import _parse_period, _filter_records_by_period, _format_period_label
    from app.services.agent.agent_records import query_records

    today = datetime.now(timezone.utc)
    period = _parse_period(text, today)

    if not period:
        await bot.send_message(
            None,
            "Не распознал дату. Укажите, например:\n• 15.06.2026\n• с 01.06 по 14.06",
            chat_id=chat_id,
            notify=False,
        )
        return True

    start, end = period
    label = _format_period_label(start, end)

    # Сбрасываем флаг ожидания даты
    cfg = dict(agent.config or {})
    cfg.pop("secretary_pending_report", None)
    agent.config = cfg

    records = query_records(agent, "records", limit=5000)
    filtered = _filter_records_by_period(records, start, end)

    if not filtered:
        await bot.send_message(
            None,
            f"За период {label} записей не найдено.",
            chat_id=chat_id,
            notify=False,
        )
        return True

    title = f"Отчёт за {label}"
    columns = ["Категория", "Затрата", "Примечание"]
    field_keys = ["category", "amount", "note"]

    try:
        from app.services.xlsx_builder import build_report_xlsx_bytes

        rows = [[str(r.get(k, "")) for k in field_keys] for r in filtered]
        xlsx_bytes = build_report_xlsx_bytes(columns, rows, sheet_name=label[:31])
        safe_title = re.sub(r"[^\w\-]", "_", title)[:40]
        filename = f"{safe_title}.xlsx"

        token = await bot.upload_media(xlsx_bytes, filename, "file")
        if token:
            attachment = {"type": "file", "payload": {"token": token}}
            await bot.send_message(
                None,
                f"{title} — {len(filtered)} записей:",
                attachments=[attachment],
                chat_id=chat_id,
                notify=False,
            )
        else:
            await bot.send_message(
                None,
                "⚠️ Не удалось загрузить файл отчёта.",
                chat_id=chat_id,
                notify=False,
            )
    except Exception as exc:
        logger.exception("Secretary date report failed agent=%s: %s", agent.id, exc)
        await bot.send_message(
            None,
            "⚠️ Ошибка при формировании отчёта.",
            chat_id=chat_id,
            notify=False,
        )

    return True
