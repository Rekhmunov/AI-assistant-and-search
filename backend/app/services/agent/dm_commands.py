"""Команды боту в личном чате MAX (несколько агентов — по префиксу)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.services.agent.content import build_dm_command_content
from app.services.agent.max_compliance import dm_command_allowed
from app.services.agent.profile import agent_config, normalize_dm_command
from app.services.agent.reminders import effective_max_user_id
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


def parse_dm_command(text: str) -> tuple[str | None, str]:
    """Возвращает (команда, аргументы). /news arg → ('news', 'arg')."""
    raw = (text or "").strip()
    if not raw:
        return None, ""
    parts = raw.split(maxsplit=1)
    head = parts[0].lower()
    if head.startswith("/"):
        head = head[1:]
    args = parts[1].strip() if len(parts) > 1 else ""
    return head or None, args


async def find_dm_agent_for_command(
    db: AsyncSession,
    *,
    max_user_id: int,
    command: str | None,
) -> AgentInstance | None:
    if not command:
        return None
    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.max_user_id == max_user_id,
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.role == AgentRole.DM_ASSISTANT.value,
        )
    )
    agents = list(result.scalars().all())
    if not agents:
        return None

    matches: list[AgentInstance] = []
    for agent in agents:
        cfg = agent_config(agent)
        cmd = normalize_dm_command(cfg.get("dm_command"))
        if cmd and cmd == command:
            matches.append(agent)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.warning("Ambiguous dm command %s for user %s", command, max_user_id)
        return matches[0]
    return None


async def list_dm_commands_for_user(db: AsyncSession, *, max_user_id: int) -> list[str]:
    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.max_user_id == max_user_id,
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.role == AgentRole.DM_ASSISTANT.value,
        )
    )
    cmds: list[str] = []
    for agent in result.scalars().all():
        cfg = agent_config(agent)
        cmd = normalize_dm_command(cfg.get("dm_command"))
        if cmd:
            cmds.append(cmd)
    return sorted(set(cmds))


async def handle_dm_message(
    db: AsyncSession,
    redis_client,
    *,
    max_user_id: int,
    text: str,
    bot: MaxBotService | None = None,
) -> bool:
    """
    Обрабатывает личное сообщение боту.
    Возвращает True, если ответ отправлен (не показывать welcome-поведение).
    """
    bot = bot or MaxBotService()
    low = (text or "").strip().lower()

    if low in {"help", "помощь", "команды", "commands", "/help"}:
        cmds = await list_dm_commands_for_user(db, max_user_id=max_user_id)
        if not cmds:
            return False
        lines = "\n".join(f"• /{c}" for c in cmds)
        await bot.send_message(
            max_user_id,
            f"Доступные команды:\n{lines}\n\nОтправьте команду, чтобы запустить агента.",
        )
        return True

    command, _args = parse_dm_command(text)
    if not await dm_command_allowed(max_user_id):
        return True

    agent = await find_dm_agent_for_command(db, max_user_id=max_user_id, command=command)
    if not agent:
        return False

    from app.models.user import User

    user_result = await db.execute(select(User).where(User.max_user_id == max_user_id).limit(1))
    user = user_result.scalar_one_or_none()
    if not user:
        await bot.send_message(max_user_id, "Привяжите MAX в профиле Glosix, чтобы использовать команды.")
        return True

    if not effective_max_user_id(agent):
        agent.max_user_id = max_user_id

    try:
        content = await build_dm_command_content(db, redis_client, user, agent, bot=bot)
        result = await bot.send_message(
            max_user_id,
            content.text,
            attachments=content.attachments or None,
        )
        if not result.ok:
            await bot.send_message(max_user_id, "Не удалось выполнить команду. Попробуйте позже.")
    except Exception as exc:
        logger.exception("DM command failed agent=%s: %s", agent.id, exc)
        await bot.send_message(max_user_id, "Ошибка при выполнении команды.")
    return True
