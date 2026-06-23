import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis
from app.services.app_settings import get_setting
from app.services.bot import MaxBotService
from app.services.bot_media import max_bot_media_attachments

logger = logging.getLogger(__name__)


async def send_bot_welcome(db: AsyncSession, max_user_id: int | None) -> bool:
    if max_user_id is None:
        return False

    redis = await get_redis()
    text = str(await get_setting("bot_welcome_text", db, redis) or "").strip()
    media_type = str(await get_setting("bot_welcome_media_type", db, redis) or "none").strip().lower()
    media_token = str(await get_setting("bot_welcome_media_token", db, redis) or "").strip()

    if not text and (media_type == "none" or not media_token):
        text = (
            "Продолжая пользоваться ботом, вы принимаете Пользовательское соглашение.\n\n"
            "Привет! Нажмите кнопку ниже, чтобы открыть Glosix."
        )

    attachments = max_bot_media_attachments(media_type, media_token)

    bot = MaxBotService()
    result = await bot.send_message(max_user_id, text, attachments)
    if not result.ok:
        logger.warning(
            "bot welcome failed for max_user_id=%s: %s",
            max_user_id,
            result.error,
        )

    # Автоматически создаём агента «Личный ассистент» если пользователь найден
    await _ensure_assistant_agent(db, redis, bot, max_user_id)

    return result.ok


async def _ensure_assistant_agent(db, redis, bot: MaxBotService, max_user_id: int) -> None:
    """
    При bot_started: если у пользователя Glosix нет активного ассистента — создаём автоматически.
    Пользователи без Glosix-аккаунта пропускаются тихо.
    """
    try:
        from sqlalchemy import select
        from app.models.user import User
        from app.models.agent import AgentInstance, AgentStatus, AgentRole

        # Ищем пользователя по max_user_id
        user_result = await db.execute(
            select(User).where(User.max_user_id == max_user_id).limit(1)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            return  # пользователь не зарегистрирован в Glosix

        # Проверяем — есть ли уже активный ассистент
        agents_result = await db.execute(
            select(AgentInstance).where(
                AgentInstance.user_id == user.id,
                AgentInstance.status == AgentStatus.ACTIVE.value,
            )
        )
        for ag in agents_result.scalars().all():
            if str((ag.config or {}).get("template") or "") == "assistant":
                return  # уже есть

        # Создаём агента
        from app.core.config import get_settings
        from datetime import datetime, timezone

        cfg = {
            "template": "assistant",
            "scope": "dm",
            "interaction_mode": "support",
        }
        agent = AgentInstance(
            user_id=user.id,
            max_user_id=max_user_id,
            role=AgentRole.DM_ASSISTANT.value,
            status=AgentStatus.ACTIVE.value,
            config=cfg,
        )
        db.add(agent)
        await db.flush()

        # Регистрируем slash-команды в MAX
        try:
            await bot.set_commands([
                {"name": "new", "description": "Начать новый диалог"},
                {"name": "history", "description": "Последние беседы"},
            ])
        except Exception as exc:
            logger.warning("ensure_assistant: set_commands failed: %s", exc)

        await db.commit()
        logger.info("Auto-created assistant agent for user=%s max_user_id=%s", user.id, max_user_id)

    except Exception as exc:
        logger.warning("ensure_assistant_agent failed max_user_id=%s: %s", max_user_id, exc)
