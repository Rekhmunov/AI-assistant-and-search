"""Регрессия: secretary не должен молчать при ошибке подтверждения записи."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.agent import AgentInstance
from app.models.user import User
from app.services.agent.agent_tools import execute_agent_tool
from app.services.bot import BotSendResult


@pytest.mark.asyncio
async def test_store_agent_record_no_outbound_sent_when_confirm_fails():
    agent_id = uuid4()
    user_id = uuid4()
    agent = AgentInstance(
        id=agent_id,
        user_id=user_id,
        role="dm_assistant",
        status="active",
        config={"template": "secretary"},
        max_chat_id=-75894933081545,
    )
    user = User(id=user_id, max_user_id=12345)

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(
        side_effect=[
            BotSendResult(ok=False, error="attachment.not.ready"),
            BotSendResult(ok=False, error="send failed"),
        ]
    )
    mock_bot.make_keyboard_attachment = MagicMock(return_value={"type": "inline_keyboard", "payload": {}})

    with patch("app.services.agent.agent_tools._tool_store_record") as mock_store:
        mock_store.return_value = {
            "ok": True,
            "result": {
                "entry": {
                    "_id": "rec-1",
                    "category": "Тест",
                    "amount": 1000,
                }
            },
        }
        with patch("app.services.agent.agent_spec.load_agent_spec") as mock_load:
            mock_load.return_value = MagicMock(facts=[])
            with patch("app.services.agent.agent_spec.save_agent_spec"):
                result = await execute_agent_tool(
                    MagicMock(),
                    MagicMock(),
                    user,
                    agent,
                    "store_agent_record",
                    {"table": "records", "data": {"amount": 1000, "category": "Тест"}},
                    thread_id=uuid4(),
                    allow_test_send=True,
                    runtime_chat_id=-75894933081545,
                    author="user",
                    bot=mock_bot,
                )

    assert result.get("ok") is True
    assert "outbound_sent" not in result
    assert mock_bot.send_message.await_count == 2
