"""Исполнение инструментов агента (MAX, веб, журнал)."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentReminder, AgentRole, AgentStatus
from app.models.message import Message
from app.models.user import User
from app.services.agent.activity_log import list_agent_activity_logs
from app.services.agent.agent_security import AgentSecurityError, validate_tool_call
from app.services.agent.agent_status import StatusCallback
from app.services.agent.intent_hints import _extract_max_chat_id
from app.services.agent.max_probe import probe_max_chat, resolve_channel_link
from app.services.agent.max_errors import explain_max_send_error, explain_security_error
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


async def execute_agent_tool(
    db: AsyncSession,
    redis_client,
    user: User,
    agent: AgentInstance,
    tool: str,
    args: dict[str, Any],
    *,
    thread_id: UUID,
    allow_test_send: bool,
    bot: MaxBotService | None = None,
    user_message: str = "",
    runtime_chat_id: int | None = None,
    author: str = "",
    on_status: StatusCallback | None = None,
) -> dict[str, Any]:
    bot = bot or MaxBotService()
    message_chat_id = _extract_max_chat_id(user_message)
    try:
        safe_args = validate_tool_call(
            tool,
            args,
            agent=agent,
            user=user,
            message_chat_id=message_chat_id,
            allow_test_send=allow_test_send,
        )
    except AgentSecurityError as exc:
        code = str(exc)
        return {
            "ok": False,
            "error": code,
            "error_human": explain_security_error(code),
            "tool": tool,
        }

    name = str(tool).strip().lower()
    try:
        if name == "max_probe_chat":
            return await _tool_max_probe_chat(bot, safe_args, allow_test_send=allow_test_send)
        if name == "max_send_test":
            return await _tool_max_send_test(bot, safe_args)
        if name == "max_get_chat":
            return await _tool_max_get_chat(bot, safe_args)
        if name == "max_list_bot_chats":
            return await _tool_max_list_bot_chats(db, user, agent)
        if name == "max_resolve_channel_link":
            return await _tool_resolve_link(bot, safe_args, agent=agent)
        if name == "max_read_activity_logs":
            return await _tool_read_logs(db, thread_id=thread_id, user_id=user.id)
        if name == "web_search":
            return await _tool_web_search(db, redis_client, user, safe_args, on_status=on_status)
        if name == "read_thread_summary":
            return await _tool_thread_summary(db, thread_id=thread_id)
        if name == "max_send_file":
            return await _tool_max_send_file(
                db,
                redis_client,
                user,
                safe_args,
                bot=bot,
            )
        if name == "max_send_message":
            return await _tool_max_send_message(bot, safe_args, agent=agent)
        if name == "max_confirm_record":
            return await _tool_max_confirm_record(bot, agent, safe_args)
        if name == "max_send_date_picker":
            return await _tool_max_send_date_picker(bot, agent, safe_args)
        if name == "search_thread_history":
            return await _tool_search_thread_history(db, thread_id=thread_id, args=safe_args)
        if name == "generate_post_draft":
            return await _tool_generate_post_draft(db, redis_client, agent, bot, safe_args, runtime_chat_id)
        if name == "query_post_history":
            return _tool_query_post_history(agent)
        if name == "store_agent_record":
            result = _tool_store_record(agent, safe_args, author=author, chat_id=runtime_chat_id)
            # Для агента «Учет затрат»: автоматически отправляем подтверждение с кнопкой удаления.
            # Это гарантирует единый формат ответа независимо от поведения LLM.
            if (
                result.get("ok")
                and str((agent.config or {}).get("template") or "") == "secretary"
                and runtime_chat_id is not None
                and allow_test_send
            ):
                entry = (result.get("result") or {}).get("entry") or {}
                record_id = str(entry.get("_id") or "")
                category = str(entry.get("category") or "")
                amount = entry.get("amount", "")
                amt_str = str(int(amount)) if isinstance(amount, float) and amount == int(amount) else str(amount)
                confirm_text = f"✅ Записано в категорию: {category} — {amt_str}"
                confirm_result = await _tool_max_confirm_record(bot, agent, {
                    "text": confirm_text,
                    "chat_id": runtime_chat_id,
                    "record_id": record_id,
                })
                # Сохраняем message_id подтверждения в запись для последующего редактирования
                confirm_msg_id = (confirm_result.get("result") or {}).get("message_id")
                if confirm_msg_id and record_id:
                    from app.services.agent.agent_records import patch_record_field
                    patch_record_field(agent, str(safe_args.get("table") or "records"), record_id, "_mid", confirm_msg_id)
                # Очищаем pending_entry из памяти агента — LLM не успеет вызвать
                # update_agent_memory из-за break в tool loop после outbound_sent=True
                from app.services.agent.agent_spec import load_agent_spec, save_agent_spec
                _spec = load_agent_spec(agent)
                _spec.facts = [f for f in _spec.facts if not f.lower().startswith("pending_entry")]
                save_agent_spec(agent, _spec)
                result["outbound_sent"] = True
            return result
        if name == "query_agent_records":
            return _tool_query_records(agent, safe_args)
        if name == "update_agent_memory":
            return _tool_update_memory(agent, safe_args)
        if name == "read_max_api_docs":
            return _tool_read_max_api_docs(safe_args)
        if name == "read_knowledge_base":
            return await _tool_read_knowledge_base(db, agent, safe_args)
        if name == "read_group_history":
            return await _tool_read_group_history(bot, safe_args)
        if name == "query_secretary_records":
            return await _tool_query_secretary_records(db, user, safe_args)
        if name == "save_agent_instructions":
            return _tool_save_agent_instructions(agent, safe_args)
        if name == "delete_agent_record":
            return _tool_delete_agent_record(agent, safe_args)
    except Exception as exc:
        logger.exception("Agent tool %s failed: %s", name, exc)
        raw = str(exc)[:300]
        return {
            "ok": False,
            "error": raw,
            "error_human": explain_max_send_error(raw),
            "tool": name,
        }

    return {
        "ok": False,
        "error": "unknown_tool",
        "error_human": explain_security_error("unknown_tool"),
        "tool": name,
    }


async def _tool_max_probe_chat(bot: MaxBotService, args: dict, *, allow_test_send: bool = False) -> dict:
    chat_id = int(args["chat_id"])
    # send_test разрешён только если allow_test_send=True — те же правила что у max_send_test
    send_test = bool(args.get("send_test")) and allow_test_send
    probe = await probe_max_chat(bot, chat_id, send_test=send_test)
    return {"ok": probe.get("ok", False), "tool": "max_probe_chat", "result": probe}


async def _tool_max_send_test(bot: MaxBotService, args: dict) -> dict:
    chat_id = int(args["chat_id"])
    probe = await probe_max_chat(bot, chat_id, send_test=True)
    return {"ok": probe.get("ok", False), "tool": "max_send_test", "result": probe}


async def _tool_max_get_chat(bot: MaxBotService, args: dict) -> dict:
    chat_id = int(args["chat_id"])
    chat = await bot.get_chat(chat_id)
    if not chat:
        return {
            "ok": False,
            "tool": "max_get_chat",
            "error": explain_max_send_error("404", chat_id=chat_id),
        }
    safe = {
        k: chat.get(k)
        for k in ("chat_id", "type", "status", "title", "participants_count", "is_public", "link")
    }
    admin = await bot.check_bot_is_group_admin(chat_id)
    safe["bot_is_admin"] = admin
    return {"ok": True, "tool": "max_get_chat", "result": safe}


async def _tool_max_list_bot_chats(
    db: AsyncSession,
    user: User,
    agent: AgentInstance,
) -> dict:
    """
    Возвращает список чатов, в которых бот был замечен.

    GET /chats устарел с июня 2026. GET /subscriptions возвращает webhook-подписки
    (URL + event types), а НЕ список чатов. Поэтому берём chat_id из:
    1. AgentInstance записей текущего пользователя (из bot_added событий)
    2. Конфига текущего агента
    """
    chats: list[dict] = []
    seen: set[int] = set()

    # Чаты из конфига текущего агента
    cfg = dict(agent.config or {})
    for key in ("max_chat_id", "registered_group_chat_id", "thread_chat_id"):
        raw = cfg.get(key)
        if raw is not None:
            try:
                cid = int(raw)
                if cid > 0 and cid not in seen:
                    seen.add(cid)
                    chats.append({"chat_id": cid, "source": "agent_config"})
            except (ValueError, TypeError):
                pass

    # Чаты из всех агентов пользователя
    try:
        from sqlalchemy import select as sa_select
        from app.models.agent import AgentStatus

        result = await db.execute(
            sa_select(AgentInstance).where(
                AgentInstance.user_id == user.id,
                AgentInstance.status.in_([
                    AgentStatus.ACTIVE.value,
                    AgentStatus.COLLECTING.value,
                ]),
                AgentInstance.max_chat_id.isnot(None),
            )
        )
        for inst in result.scalars().all():
            cid = int(inst.max_chat_id)
            if cid > 0 and cid not in seen:
                seen.add(cid)
                chats.append({
                    "chat_id": cid,
                    "source": "agent_instance",
                    "role": inst.role,
                })
    except Exception as exc:
        logger.warning("max_list_bot_chats DB query failed: %s", exc)

    note = (
        "Список содержит чаты, зарегистрированные через webhook bot_added. "
        "Если группы нет в списке — добавьте бота в группу или пришлите её ссылку."
    )
    return {
        "ok": True,
        "tool": "max_list_bot_chats",
        "result": {"chats": chats, "count": len(chats), "note": note},
    }


async def _tool_resolve_link(bot: MaxBotService, args: dict, *, agent: AgentInstance) -> dict:
    resolved = await resolve_channel_link(bot, str(args["link"]))
    if resolved.get("ok") and resolved.get("chat_id"):
        cid = int(resolved["chat_id"])
        agent.max_chat_id = cid
        cfg = dict(agent.config or {})
        cfg["max_chat_id"] = cid
        cfg["registered_group_chat_id"] = cid
        agent.config = cfg
    return {"ok": resolved.get("ok", False), "tool": "max_resolve_channel_link", "result": resolved}


async def _tool_read_logs(db: AsyncSession, *, thread_id: UUID, user_id: UUID) -> dict:
    rows = await list_agent_activity_logs(db, thread_id=thread_id, user_id=user_id)
    items = [
        {
            "event": r.event,
            "level": r.level,
            "details": r.details,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows[:30]
    ]
    return {"ok": True, "tool": "max_read_activity_logs", "result": {"items": items}}


async def _tool_web_search(
    db: AsyncSession,
    redis_client,
    user: User,
    args: dict,
    *,
    on_status: StatusCallback | None = None,
) -> dict:
    from app.services.agent.agent_search import run_agent_glosix_search

    topic = str(args["query"])
    search = await run_agent_glosix_search(
        db,
        redis_client,
        user,
        topic,
        on_status=on_status,
    )
    return {
        "ok": True,
        "tool": "web_search",
        "result": {
            "text": search.text[:4000],
            "sources": search.sources[:12],
            "sources_block": search.sources_block,
        },
    }


async def _tool_max_send_file(
    db: AsyncSession,
    redis_client,
    user: User,
    args: dict,
    *,
    bot: MaxBotService,
) -> dict:
    from app.services.agent.document_delivery import (
        build_document_delivery_content,
        build_image_delivery_content,
    )

    send_user_id: int | None = args.get("user_id")
    send_chat_id: int | None = args.get("chat_id")
    instruction = str(args["instruction"])
    fmt = str(args.get("format") or "docx")
    try:
        if fmt == "image":
            result = await build_image_delivery_content(
                instruction, bot=bot, db=db, user=user, redis_client=redis_client
            )
        else:
            result = await build_document_delivery_content(
                db,
                redis_client,
                user,
                instruction,
                output_format=fmt,
                bot=bot,
            )
        if not result.attachments:
            return {
                "ok": False,
                "tool": "max_send_file",
                "error": result.text or "Не удалось подготовить файл",
            }
        # Изображение + кнопка «Скачать» (inline_keyboard после фото)
        send_attachments = result.attachments[:]
        if result.keyboard:
            send_attachments.append(result.keyboard)

        if send_user_id is not None:
            # Личное сообщение
            send = await bot.send_message(
                int(send_user_id),
                result.text or "Файл",
                attachments=send_attachments,
                notify=True,
            )
            dest: dict = {"user_id": send_user_id}
            err_explain = explain_max_send_error(send.error, user_id=int(send_user_id))
        else:
            send = await bot.send_message(
                None,
                result.text or "Файл",
                attachments=send_attachments,
                chat_id=int(send_chat_id),
                notify=False,
            )
            dest = {"chat_id": send_chat_id}
            err_explain = explain_max_send_error(send.error, chat_id=int(send_chat_id))

        file_result: dict = {**dest, "format": fmt, "message_id": send.message_id}
        if not send.ok:
            file_result["error"] = send.error
            file_result["error_human"] = err_explain
        else:
            file_result["attachments"] = result.attachments
        return {"ok": send.ok, "tool": "max_send_file", "result": file_result}
    except Exception as exc:
        logger.exception("max_send_file failed chat_id=%s: %s", chat_id, exc)
        return {"ok": False, "tool": "max_send_file", "error": str(exc)[:300]}


def _parse_clarify_text(text: str) -> tuple[str | None, list[str]]:
    """
    Разбирает текст уточнения категории в формате:
      ❓ К какой категории отнести «...»?
      • Категория 1
      • Категория 2
      Напиши «Отмена», если ...

    Возвращает (заголовок, [категория1, категория2, ...]) или (None, []) если формат не совпадает.
    """
    import re as _re
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None, []
    header = lines[0]
    # Проверяем, что первая строка — вопрос о категории
    if not (header.startswith("❓") or ("к какой категории" in header.lower()) or ("категори" in header.lower())):
        return None, []
    categories = []
    for line in lines[1:]:
        # Строки вида «• Категория» или «- Категория» или «1. Категория»
        m = _re.match(r"^[•\-\*]\s+(.+)$", line) or _re.match(r"^\d+[.)]\s+(.+)$", line)
        if m:
            cat = m.group(1).strip()
            # Пропускаем строку «Напиши «Отмена»...» и подобные
            if "напиши" in cat.lower() or "отмена" in cat.lower() or len(cat) > 80:
                continue
            categories.append(cat)
    return header, categories


async def _tool_max_send_message(
    bot: MaxBotService,
    args: dict,
    *,
    agent: "AgentInstance | None" = None,
) -> dict:
    text = str(args["text"])
    user_id: int | None = args.get("user_id")
    chat_id: int | None = args.get("chat_id")

    # Для агента «Учет затрат»: перехватываем текст с предложением выбора категории
    # и заменяем его на inline-клавиатуру с кнопками.
    if agent is not None and str((agent.config or {}).get("template") or "") == "secretary":
        header, categories = _parse_clarify_text(text)
        if header and categories:
            agent_id_str = str(agent.id)
            rows = [
                [{"type": "callback", "text": cat,
                  "payload": f"secretary:clarify:{agent_id_str}:{cat}"}]
                for cat in categories
            ]
            rows.append([{"type": "callback", "text": "❌ Отмена",
                          "payload": f"secretary:clarify_cancel:{agent_id_str}"}])
            keyboard = MaxBotService.make_keyboard_attachment(rows)
            # Упрощаем заголовок: убираем префикс «❓» если он уже есть
            clean_header = header.lstrip("❓").strip()
            dest_user = int(user_id) if user_id is not None else None
            dest_chat = int(chat_id) if chat_id is not None else None
            if dest_user is not None:
                send = await bot.send_message(dest_user, clean_header, attachments=[keyboard], notify=True)
                result: dict = {"user_id": user_id, "message_id": send.message_id}
                if not send.ok:
                    result["error"] = send.error
                    result["error_human"] = explain_max_send_error(send.error, user_id=dest_user)
                return {"ok": send.ok, "tool": "max_send_message", "result": result}
            else:
                send = await bot.send_message(None, clean_header, attachments=[keyboard], chat_id=dest_chat, notify=False)
                result = {"chat_id": chat_id, "message_id": send.message_id}
                if not send.ok:
                    result["error"] = send.error
                    result["error_human"] = explain_max_send_error(send.error, chat_id=dest_chat)
                return {"ok": send.ok, "tool": "max_send_message", "result": result}

    if user_id is not None:
        # Личное сообщение: MAX API требует user_id, не chat_id
        send = await bot.send_message(int(user_id), text, notify=True)
        result = {"user_id": user_id, "message_id": send.message_id}
        if not send.ok:
            result["error"] = send.error
            result["error_human"] = explain_max_send_error(send.error, user_id=int(user_id))
        return {"ok": send.ok, "tool": "max_send_message", "result": result}
    else:
        # Групповое сообщение
        send = await bot.send_message(None, text, chat_id=int(chat_id), notify=False)
        result = {"chat_id": chat_id, "message_id": send.message_id}
        if not send.ok:
            result["error"] = send.error
            result["error_human"] = explain_max_send_error(send.error, chat_id=int(chat_id))
        return {"ok": send.ok, "tool": "max_send_message", "result": result}


async def _tool_max_confirm_record(
    bot: MaxBotService,
    agent: AgentInstance,
    args: dict,
) -> dict:
    """
    Отправляет подтверждение записи с кнопкой «🗑 Удалить».
    Инструмент только для агента «Учет затрат» (template=secretary).
    Аргументы: text, chat_id, record_id.
    """
    text = str(args.get("text") or "✅ Записано")
    chat_id = int(args["chat_id"])
    record_id = str(args.get("record_id") or "")

    keyboard = bot.make_keyboard_attachment([
        [{"type": "callback", "text": "🗑 Удалить запись", "payload": f"secretary:delete:{agent.id}:{record_id}"}]
    ])
    send = await bot.send_message(None, text, attachments=[keyboard], chat_id=chat_id, notify=False)
    result: dict = {"chat_id": chat_id, "message_id": send.message_id}
    if not send.ok:
        from app.services.agent.max_errors import explain_max_send_error
        result["error"] = send.error
        result["error_human"] = explain_max_send_error(send.error, chat_id=chat_id)
    return {"ok": send.ok, "tool": "max_confirm_record", "result": result}


async def _tool_max_send_date_picker(
    bot: MaxBotService,
    agent: AgentInstance,
    args: dict,
) -> dict:
    """
    Спрашивает период для отчёта простым текстом (без кнопок).
    Ставит флаг secretary_pending_report — следующее сообщение
    будет распознано как дата/диапазон и обработано детерминированно.
    """
    chat_id = int(args["chat_id"])

    # Ставим флаг: следующее сообщение в группе — это ввод периода
    cfg = dict(agent.config or {})
    cfg["secretary_pending_report"] = True
    agent.config = cfg

    send = await bot.send_message(
        None,
        "За какой период сформировать отчёт?",
        chat_id=chat_id,
        notify=False,
    )
    result: dict = {"chat_id": chat_id}
    if not send.ok:
        from app.services.agent.max_errors import explain_max_send_error
        result["error"] = send.error
        result["error_human"] = explain_max_send_error(send.error, chat_id=chat_id)
    return {"ok": send.ok, "tool": "max_send_date_picker", "result": result}


async def _tool_search_thread_history(db: AsyncSession, *, thread_id: UUID, args: dict) -> dict:
    from app.services.agent.thread_memory import search_thread_history_tool

    return await search_thread_history_tool(db, thread_id, str(args["query"]))


def _tool_store_record(
    agent: AgentInstance,
    args: dict,
    *,
    author: str,
    chat_id: int | None,
) -> dict:
    from app.services.agent.agent_records import store_record

    entry = store_record(
        agent,
        str(args["table"]),
        dict(args["data"]),
        author=author,
        chat_id=chat_id,
    )
    return {"ok": True, "tool": "store_agent_record", "result": {"entry": entry}}


def _tool_query_records(agent: AgentInstance, args: dict) -> dict:
    from app.services.agent.agent_records import query_records

    rows = query_records(
        agent,
        str(args["table"]),
        category=str(args["category"]) if args.get("category") else None,
    )
    return {"ok": True, "tool": "query_agent_records", "result": {"items": rows, "count": len(rows)}}


def _tool_delete_agent_record(agent: AgentInstance, args: dict) -> dict:
    """Удаляет запись из таблицы агента."""
    from app.services.agent.agent_records import delete_record

    table = str(args.get("table") or "default")
    last = bool(args.get("last"))
    index = int(args["index"]) if args.get("index") is not None else None
    match = dict(args["match"]) if isinstance(args.get("match"), dict) else None

    result = delete_record(agent, table, last=last, index=index, match=match)
    return {"ok": True, "tool": "delete_agent_record", "result": result}


def _tool_save_agent_instructions(agent: AgentInstance, args: dict) -> dict:
    """Сохраняет текст как инструкцию агента (support_instructions в config)."""
    text = str(args.get("text") or "").strip()
    if not text:
        return {"ok": False, "tool": "save_agent_instructions", "error": "Текст инструкции пустой"}
    cfg = dict(agent.config or {})
    cfg["support_instructions"] = text
    agent.config = cfg
    agent.instruction_text = text[:500]
    return {"ok": True, "tool": "save_agent_instructions", "result": {"saved_chars": len(text)}}


async def _tool_query_secretary_records(
    db: AsyncSession,
    user: User,
    args: dict,
) -> dict:
    """Читает записи секретаря (dm_assistant с template=secretary) того же пользователя."""
    from app.services.agent.agent_records import query_records
    from sqlalchemy import select

    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.user_id == user.id,
            AgentInstance.role == AgentRole.DM_ASSISTANT.value,
            AgentInstance.status == AgentStatus.ACTIVE.value,
        )
    )
    all_agents = result.scalars().all()
    secretary_agents = [a for a in all_agents if str((a.config or {}).get("template") or "") == "secretary"]

    if not secretary_agents:
        return {"ok": False, "tool": "query_secretary_records", "error": "Активный секретарь не найден"}

    table = str(args.get("table") or "default")
    category = str(args["category"]) if args.get("category") else None
    limit = int(args.get("limit") or 100)

    all_rows: list[dict] = []
    for sec_agent in secretary_agents:
        rows = query_records(sec_agent, table, category=category, limit=limit)
        chat_id = sec_agent.max_chat_id
        for row in rows:
            row = dict(row)
            if chat_id and "chat_id" not in row:
                row["chat_id"] = chat_id
            all_rows.append(row)

    all_rows.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
    return {"ok": True, "tool": "query_secretary_records", "result": {"items": all_rows[:limit], "count": len(all_rows)}}


def _tool_update_memory(agent: AgentInstance, args: dict) -> dict:
    from app.services.agent.agent_spec import append_fact, load_agent_spec, save_agent_spec

    spec = load_agent_spec(agent)
    append_fact(spec, str(args["note"]))
    save_agent_spec(agent, spec)
    return {"ok": True, "tool": "update_agent_memory", "result": {"facts": spec.facts[-5:]}}


async def _tool_thread_summary(db: AsyncSession, *, thread_id: UUID) -> dict:
    result = await db.execute(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at.desc()).limit(24)
    )
    msgs = list(reversed(result.scalars().all()))
    lines = [f"{m.role.value}: {m.content[:400]}" for m in msgs]
    return {"ok": True, "tool": "read_thread_summary", "result": {"messages": lines}}


async def _tool_read_group_history(bot: MaxBotService, args: dict) -> dict:
    """
    Читает последние N сообщений из группы MAX.
    Используется секретарём для восстановления пропущенных записей.
    Требует бот — администратор группы.
    """
    chat_id = int(args["chat_id"])
    count = int(args.get("count") or 50)
    from_ts = args.get("from_timestamp")

    messages = await bot.get_group_messages(
        chat_id,
        from_timestamp=int(from_ts) if from_ts is not None else None,
        count=count,
    )

    # Упрощаем до текста и временной метки для LLM
    simplified = []
    for m in messages:
        body = m.get("body") or {}
        text = body.get("text") or m.get("text") or ""
        sender = m.get("sender") or {}
        is_bot = sender.get("is_bot", False)
        timestamp = body.get("timestamp") or m.get("timestamp")
        if text and not is_bot:
            simplified.append({
                "text": text[:500],
                "timestamp": timestamp,
                "author": sender.get("name") or "пользователь",
            })

    return {
        "ok": True,
        "tool": "read_group_history",
        "result": {
            "messages": simplified[:50],
            "count": len(simplified),
            "note": "Сообщения от пользователей, не от бота. Сравни с записями в БД для поиска пропусков.",
        },
    }


async def _tool_read_knowledge_base(db: AsyncSession, agent: AgentInstance, args: dict) -> dict:
    """
    Читает документы из базы знаний ТЕКУЩЕГО агента.
    Изоляция гарантирована: запрос идёт строго по agent.id текущего треда.
    Нельзя получить данные другого агента или другого пользователя.
    """
    from app.services.agent.knowledge import retrieve_knowledge_context

    query = str(args.get("query") or "").strip()
    cfg = dict(agent.config or {})
    sources = cfg.get("knowledge_sources") or []
    chunk_count = int(cfg.get("knowledge_chunk_count") or 0)

    if not chunk_count:
        return {
            "ok": True,
            "tool": "read_knowledge_base",
            "result": {
                "has_knowledge": False,
                "content": "",
                "sources": [],
                "note": "База знаний пуста. Пользователь может загрузить документы кнопкой «+» в этом треде.",
            },
        }

    context = await retrieve_knowledge_context(db, agent, query, limit=12)
    return {
        "ok": True,
        "tool": "read_knowledge_base",
        "result": {
            "has_knowledge": bool(context),
            "content": context[:8000],
            "sources": sources,
            "chunk_count": chunk_count,
        },
    }


def _tool_read_max_api_docs(args: dict) -> dict:
    from app.services.agent.max_docs import get_max_docs

    section = str(args.get("section") or "").strip()
    content = get_max_docs(section or None)
    return {
        "ok": True,
        "tool": "read_max_api_docs",
        "result": {"content": content[:8000], "section": section or "full"},
    }


async def agent_runtime_diagnostics(db: AsyncSession, agent: AgentInstance) -> dict:
    """Снимок для диагностики активного агента."""
    cfg = dict(agent.config or {}) if isinstance(agent.config, dict) else {}
    rem_result = await db.execute(
        select(AgentReminder)
        .where(AgentReminder.agent_id == agent.id)
        .order_by(AgentReminder.run_at.desc())
        .limit(5)
    )
    reminders = [
        {
            "run_at": r.run_at.isoformat(),
            "status": r.status,
            "last_error": r.last_error,
            "recurrence": r.recurrence,
        }
        for r in rem_result.scalars().all()
    ]
    return {
        "agent_status": agent.status,
        "role": agent.role,
        "max_chat_id": agent.max_chat_id,
        "next_run_at": cfg.get("next_run_at"),
        "last_dispatch_error": cfg.get("last_dispatch_error"),
        "recent_reminders": reminders,
    }


def format_tool_results_for_llm(results: list[dict]) -> str:
    """Форматирует результаты tool-вызовов для LLM.

    Для неудачных вызовов ставит error_human первым полем, чтобы LLM
    сразу видел человекочитаемое объяснение и использовал его в reply.
    """
    ordered: list[dict] = []
    for r in results:
        if not r.get("ok", True) and "error_human" in r:
            # Переупорядочиваем: error_human идёт первым
            entry = {"ok": False, "error_human": r["error_human"], "tool": r.get("tool", "?")}
            if "error" in r:
                entry["error"] = r["error"]
            nested = r.get("result")
            if nested:
                entry["result"] = nested
            ordered.append(entry)
        else:
            ordered.append(r)
    return json.dumps(ordered, ensure_ascii=False, indent=0)[:12000]


# ─────────────────────────────────────────────────────────────────────────────
# Инструменты агента «Постинг»
# ─────────────────────────────────────────────────────────────────────────────

async def _tool_generate_post_draft(
    db,
    redis_client,
    agent: Any,
    bot: Any,
    args: dict,
    approval_chat_id: int | None,
) -> dict:
    """Генерирует черновик поста и отправляет его на согласование."""
    import uuid as _uuid
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

    from app.services.agent.poster_executor import _topic_text
    topic_obj = args.get("topic") or _pick_next_topic(agent)
    topic = _topic_text(topic_obj)  # always a plain string for storage/UI

    try:
        llm, _, _, _, _ = await resolve_agent_providers(db, redis_client)
        post_text = await generate_post(agent, topic_obj, llm, db=db, redis_client=redis_client)
    except Exception as exc:
        return {"ok": False, "tool": "generate_post_draft", "error": str(exc)}

    post_id = str(_uuid.uuid4())
    save_post_to_history(agent, post_id=post_id, topic=topic, text=post_text, status="draft")

    approval_mode = get_approval_mode(agent)
    channel_id = get_poster_channel_id(agent)

    # Generate image if ai mode configured
    image_bytes = await generate_poster_image(agent, topic, post_text, db=db, redis_client=redis_client)

    if approval_mode == "auto" and channel_id:
        ok = await publish_to_channel(bot, channel_id=channel_id, text=post_text, image_bytes=image_bytes)
        if ok:
            update_post_status(agent, post_id, "published")
            return {"ok": True, "tool": "generate_post_draft", "result": "Пост опубликован автоматически.", "outbound_sent": True}
        return {"ok": False, "tool": "generate_post_draft", "error": "Не удалось опубликовать пост в канал."}

    # С согласованием — отправляем в group chat или DM владельца
    save_pending_draft(agent, post_id=post_id, topic=topic, text=post_text)
    msg_id = await send_draft_for_approval(
        agent, db, bot,
        post_id=post_id, topic=topic, text=post_text,
    )
    if msg_id:
        save_pending_draft(agent, post_id=post_id, topic=topic, text=post_text, draft_message_id=msg_id)

    return {
        "ok": True,
        "tool": "generate_post_draft",
        "result": f"Черновик поста «{topic}» отправлен на согласование.",
        "outbound_sent": True,
    }


def _tool_query_post_history(agent: Any) -> dict:
    """Возвращает историю постов."""
    from app.services.agent.poster_executor import get_post_history, format_post_history
    history = get_post_history(agent)
    return {
        "ok": True,
        "tool": "query_post_history",
        "result": format_post_history(history),
    }
