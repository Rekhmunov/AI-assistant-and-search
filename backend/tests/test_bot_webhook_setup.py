"""Тесты регистрации MAX webhook."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.bot_webhook_setup import ensure_max_webhook_registered, max_webhook_public_url


def test_max_webhook_public_url():
    from app.core.config import Settings

    s = Settings(api_public_url="https://api.glosix.ru")
    with patch("app.services.bot_webhook_setup.get_settings", return_value=s):
        assert max_webhook_public_url() == "https://api.glosix.ru/api/bot/webhook"


@pytest.mark.asyncio
async def test_ensure_max_webhook_registered_calls_bot():
    from app.core.config import Settings

    settings = Settings(
        bot_token="test-token",
        max_bot_webhook_secret="secret",
        api_public_url="https://api.example.com",
        environment="production",
    )
    with patch("app.services.bot_webhook_setup.get_settings", return_value=settings):
        with patch("app.services.bot_webhook_setup.MaxBotService") as mock_cls:
            mock_bot = mock_cls.return_value
            mock_bot.register_webhook = AsyncMock(return_value=True)
            ok = await ensure_max_webhook_registered()
            assert ok is True
            mock_bot.register_webhook.assert_awaited_once_with(
                "https://api.example.com/api/bot/webhook",
                secret="secret",
            )


@pytest.mark.asyncio
async def test_ensure_max_webhook_skips_without_token():
    from app.core.config import Settings

    settings = Settings(bot_token="")
    with patch("app.services.bot_webhook_setup.get_settings", return_value=settings):
        ok = await ensure_max_webhook_registered()
        assert ok is False
