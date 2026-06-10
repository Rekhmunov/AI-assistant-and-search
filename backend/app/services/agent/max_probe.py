"""Проверка подключения бота к чату/каналу MAX перед отправкой."""

from __future__ import annotations

import logging

from app.services.agent.max_errors import explain_max_send_error
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

TEST_MESSAGE = "✅ Glosix: проверка связи с группой. Это тестовое сообщение, его можно удалить."


async def probe_max_chat(
    bot: MaxBotService,
    chat_id: int,
    *,
    send_test: bool = False,
) -> dict:
    """
    Preflight: статус чата, членство бота, права админа, опционально тестовое сообщение.
    """
    result: dict = {
        "ok": False,
        "chat_id": int(chat_id),
        "status": None,
        "title": None,
        "type": None,
        "is_channel": None,
        "bot_is_admin": None,
        "test_sent": False,
        "error": None,
        "explanation": None,
    }

    chat = await bot.get_chat(int(chat_id))
    if not chat:
        result["error"] = "chat_not_found"
        result["explanation"] = explain_max_send_error("404 not found", chat_id=chat_id)
        return result

    result["status"] = chat.get("status")
    result["title"] = chat.get("title")
    result["type"] = chat.get("type")
    status = str(chat.get("status") or "").lower()
    if status in {"removed", "left", "closed"}:
        result["error"] = f"bot_status_{status}"
        result["explanation"] = (
            f"Бот не в чате (status={status}). Добавьте Glosix в группу/канал снова."
        )
        return result

    admin = await bot.check_bot_is_group_admin(int(chat_id))
    result["bot_is_admin"] = admin

    if send_test:
        send = await bot.send_message(None, TEST_MESSAGE, chat_id=int(chat_id), notify=False)
        result["test_sent"] = send.ok
        if not send.ok:
            result["error"] = (send.error or "send_failed")[:500]
            result["explanation"] = explain_max_send_error(send.error, chat_id=chat_id)
            return result

    result["ok"] = True
    result["explanation"] = _success_summary(result)
    return result


async def resolve_channel_link(bot: MaxBotService, link: str) -> dict:
    """GET /chats/{link} — chat_id канала по публичной ссылке."""
    raw = (link or "").strip()
    if not raw:
        return {"ok": False, "error": "empty_link"}
    if "max.ru/" in raw:
        raw = raw.rsplit("/", 1)[-1]
    raw = raw.lstrip("@").strip("/")
    chat = await bot.get_chat_by_link(raw)
    if not chat:
        return {"ok": False, "error": "link_not_found", "link": raw}
    chat_id = chat.get("chat_id") or chat.get("id")
    return {
        "ok": True,
        "chat_id": int(chat_id) if chat_id is not None else None,
        "title": chat.get("title"),
        "type": chat.get("type"),
        "link": raw,
    }


def _success_summary(probe: dict) -> str:
    parts = ["Связь с чатом MAX в порядке."]
    if probe.get("title"):
        parts.append(f"Название: {probe['title']}.")
    if probe.get("status"):
        parts.append(f"Статус бота: {probe['status']}.")
    admin = probe.get("bot_is_admin")
    if admin is True:
        parts.append("Бот — администратор.")
    elif admin is False:
        parts.append("Бот в чате, но не администратор (для постинга обычно достаточно).")
    if probe.get("test_sent"):
        parts.append("Тестовое сообщение отправлено.")
    return " ".join(parts)
