"""Тесты проверки админа бота в группе MAX."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.bot import MaxBotService


def test_check_bot_is_group_admin_true():
    bot = MaxBotService(settings=MagicMock(bot_token="token"))
    bot.get_me = AsyncMock(return_value={"user_id": 42})
    bot.get_chat_members = AsyncMock(
        return_value=[{"user_id": 42, "is_bot": True, "is_admin": True, "is_owner": False}]
    )

    result = asyncio.run(bot.check_bot_is_group_admin(-100))
    assert result is True


def test_check_bot_is_group_admin_false_when_not_admin():
    bot = MaxBotService(settings=MagicMock(bot_token="token"))
    bot.get_me = AsyncMock(return_value={"user_id": 42})
    bot.get_chat_members = AsyncMock(
        return_value=[{"user_id": 42, "is_bot": True, "is_admin": False, "is_owner": False}]
    )

    result = asyncio.run(bot.check_bot_is_group_admin(-100))
    assert result is False


def test_check_bot_is_group_admin_none_without_token():
    bot = MaxBotService(settings=MagicMock(bot_token=""))
    result = asyncio.run(bot.check_bot_is_group_admin(-100))
    assert result is None
