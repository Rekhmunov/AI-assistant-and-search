import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis
from app.services.app_settings import get_setting
from app.services.bot import MaxBotService
from app.services.bot_media import max_bot_media_attachments


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
        logging.getLogger(__name__).warning(
            "bot welcome failed for max_user_id=%s: %s",
            max_user_id,
            result.error,
        )
    return result.ok
