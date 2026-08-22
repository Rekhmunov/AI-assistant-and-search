"""Регистрация MAX webhook при старте backend."""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


def max_webhook_public_url() -> str:
    settings = get_settings()
    return f"{settings.api_public_url.rstrip('/')}/api/bot/webhook"


async def ensure_max_webhook_registered() -> bool:
    """
    POST /subscriptions — перерегистрирует webhook после деплоя или смены MAX API base.
    MAX отписывает URL при 8 часах недоступности или повторных 403.
    """
    settings = get_settings()
    if not settings.bot_token.strip():
        logger.info("MAX webhook skip: bot_token not configured")
        return False

    url = max_webhook_public_url()
    secret = settings.max_bot_webhook_secret.strip() or None
    if settings.environment.strip().lower() == "production" and not secret:
        logger.warning("MAX webhook skip: MAX_BOT_WEBHOOK_SECRET not set in production")
        return False

    bot = MaxBotService()
    ok = await bot.register_webhook(url, secret=secret)
    if ok:
        logger.info("MAX webhook ensured at startup: %s", url)
    else:
        logger.warning("MAX webhook registration failed at startup: %s", url)
    return ok
