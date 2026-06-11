"""Исполнение инструментов агента (MAX, веб, журнал)."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentReminder, AgentStatus
from app.models.message import Message
from app.models.user import User
from app.services.agent.activity_log import list_agent_activity_logs
from app.services.agent.agent_security import AgentSecurityError, validate_tool_call
from app.services.agent.intent_hints import _extract_max_chat_id
from app.services.agent.max_probe import probe_max_chat, resolve_channel_link
from app.services.agent.max_errors import explain_max_send_error
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
        return {"ok": False, "error": str(exc), "tool": tool}

    name = str(tool).strip().lower()
    try:
        if name == "max_probe_chat":
            return await _tool_max_probe_chat(bot, safe_args)
        if name == "max_send_test":
            return await _tool_max_send_test(bot, safe_args)
        if name == "max_get_chat":
            return await _tool_max_get_chat(bot, safe_args)
        if name == "max_list_bot_chats":
            return await _tool_max_list_bot_chats(bot)
        if name == "max_resolve_channel_link":
            return await _tool_resolve_link(bot, safe_args, agent=agent)
        if name == "max_read_activity_logs":
            return await _tool_read_logs(db, thread_id=thread_id, user_id=user.id)
        if name == "web_search":
            return await _tool_web_search(db, redis_client, user, safe_args)
        if name == "read_thread_summary":
            return await _tool_thread_summary(db, thread_id=thread_id)
    except Exception as exc:
        logger.exception("Agent tool %s failed: %s", name, exc)
        return {"ok": False, "error": str(exc)[:300], "tool": name}

    return {"ok": False, "error": "unknown_tool", "tool": name}


async def _tool_max_probe_chat(bot: MaxBotService, args: dict) -> dict:
    chat_id = int(args["chat_id"])
    send_test = bool(args.get("send_test"))
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


async def _tool_max_list_bot_chats(bot: MaxBotService) -> dict:
    subs = await bot.list_subscriptions()
    chats = []
    for item in subs:
        if not isinstance(item, dict):
            continue
        cid = item.get("chat_id")
        if cid is not None:
            chats.append({"chat_id": cid, "url": item.get("url"), "time": item.get("time")})
    return {"ok": True, "tool": "max_list_bot_chats", "result": {"chats": chats}}


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
) -> dict:
    from app.services.agent.web_digest import build_web_digest_text

    topic = str(args["query"])
    text = await build_web_digest_text(db, redis_client, user, topic=topic, header="")
    return {"ok": True, "tool": "web_search", "result": {"text": text[:2500]}}


async def _tool_thread_summary(db: AsyncSession, *, thread_id: UUID) -> dict:
    result = await db.execute(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at.desc()).limit(24)
    )
    msgs = list(reversed(result.scalars().all()))
    lines = [f"{m.role.value}: {m.content[:400]}" for m in msgs]
    return {"ok": True, "tool": "read_thread_summary", "result": {"messages": lines}}


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
    return json.dumps(results, ensure_ascii=False, indent=0)[:12000]
