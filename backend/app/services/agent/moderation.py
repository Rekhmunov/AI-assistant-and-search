"""Модерация групповых сообщений агентом."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from app.services.agent.profile import agent_config
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)


def _moderation_rules(cfg: dict[str, Any]) -> dict[str, Any]:
    raw = cfg.get("moderation_rules")
    if isinstance(raw, dict):
        return raw
    stop_words: list[str] = []
    sw = cfg.get("moderation_stop_words")
    if isinstance(sw, str):
        stop_words = [w.strip().lower() for w in sw.split(",") if w.strip()]
    elif isinstance(sw, list):
        stop_words = [str(w).strip().lower() for w in sw if str(w).strip()]
    return {
        "stop_words": stop_words,
        "block_links": bool(cfg.get("moderation_block_links")),
        "notify_dm": cfg.get("moderation_notify_dm", True) is not False,
    }


def message_violates_rules(text: str, rules: dict[str, Any]) -> tuple[bool, str]:
    low = (text or "").lower()
    if not low.strip():
        return False, ""
    for word in rules.get("stop_words") or []:
        if word and word in low:
            return True, f"стоп-слово «{word}»"
    if rules.get("block_links") and _URL_RE.search(text):
        return True, "ссылка в сообщении"
    return False, ""


async def handle_group_moderation(
    db: AsyncSession,
    agent: AgentInstance,
    *,
    message_id: str | None,
    text: str,
    author: str,
    chat_id: int,
    bot: MaxBotService | None = None,
) -> bool:
    """Проверяет правила; при нарушении удаляет сообщение. Возвращает True если действие было."""
    cfg = agent_config(agent)
    rules = _moderation_rules(cfg)
    violated, reason = message_violates_rules(text, rules)
    if not violated:
        return False

    bot = bot or MaxBotService()
    deleted = False
    if message_id:
        result = await bot.delete_message(message_id)
        deleted = result.ok
        if not result.ok:
            logger.warning(
                "Moderation delete failed agent=%s mid=%s err=%s",
                agent.id,
                message_id,
                result.error,
            )

    if rules.get("notify_dm") and agent.max_user_id:
        preview = text[:200].replace("\n", " ")
        note = (
            f"🛡 Модерация в группе {chat_id}\n"
            f"Удалено: {deleted}\n"
            f"Причина: {reason}\n"
            f"Автор: {author}\n"
            f"Текст: {preview}"
        )
        await bot.send_message(int(agent.max_user_id), note)

    return True
