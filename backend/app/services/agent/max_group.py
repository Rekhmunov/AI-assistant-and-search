"""Проверка статуса бота и пользователя в группе MAX через API."""

from __future__ import annotations

import logging

from app.models.agent import AgentInstance, AgentRole
from app.services.agent.llm_onboarding import ChecklistState
from app.services.agent.profile import GROUP_ROLES, agent_profile
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


async def check_user_is_group_admin(
    bot: MaxBotService,
    chat_id: int,
    max_user_id: int,
) -> bool | None:
    """
    Проверяет, является ли ПОЛЬЗОВАТЕЛЬ (не бот) администратором группы.
    Используется как security-гейт перед активацией агента для публикации в группу.

    Возвращает:
    - True — пользователь администратор
    - False — пользователь в группе, но не администратор
    - None — не удалось проверить (бот не в группе или нет прав на members)
    """
    try:
        members = await bot.get_chat_members(chat_id, user_ids=[max_user_id])
        if not members:
            return None
        for m in members:
            uid = m.get("user_id") or m.get("id")
            if uid and int(uid) == int(max_user_id):
                return bool(m.get("is_admin") or m.get("is_owner"))
        # Пользователь не найден в группе
        return False
    except Exception as exc:
        logger.warning("check_user_is_group_admin failed chat_id=%s user=%s: %s", chat_id, max_user_id, exc)
        return None


async def enrich_group_admin_status(
    agent: AgentInstance,
    checklist: ChecklistState,
    *,
    bot: MaxBotService | None = None,
) -> bool | None:
    """
    Если известен max_chat_id, запрашивает MAX API (GET /chats/{id}/members).
    Возвращает True/False/None и записывает в checklist, если удалось проверить.
    """
    chat_id = checklist.max_chat_id or agent.max_chat_id
    if not chat_id:
        return None

    role = checklist.role or agent.role
    cfg = dict(agent.config or {})
    delivery = str(checklist.delivery_mode or cfg.get("delivery_mode") or "dm").lower()
    needs_check = role in GROUP_ROLES or (
        role in {AgentRole.NEWS_DIGEST.value, AgentRole.IMAGE_POST.value} and delivery == "group"
    )
    if not needs_check:
        return checklist.bot_is_group_admin

    if checklist.bot_is_group_admin is not None:
        return checklist.bot_is_group_admin

    bot = bot or MaxBotService()
    result = await bot.check_bot_is_group_admin(int(chat_id))
    if result is not None:
        checklist.bot_is_group_admin = result
    return result
