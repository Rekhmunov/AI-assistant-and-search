"""Тесты dispatch напоминаний агента."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.agent import AgentInstance, AgentReminder, AgentRole, AgentStatus
from app.services.agent.content import DeliveryContent
from app.services.agent.dispatch import dispatch_due_reminders
from app.services.bot import BotSendResult


def _agent(**kwargs) -> AgentInstance:
    defaults = {
        "id": uuid.uuid4(),
        "thread_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "max_user_id": 0,
        "status": AgentStatus.ACTIVE.value,
        "role": AgentRole.NEWS_DIGEST.value,
        "config": {
            "delivery_mode": "group",
            "search_topic": "искусственный интеллект",
            "content_pipeline": "web_digest_images",
            "schedule_text": "каждый час",
        },
        "instruction_text": "",
        "max_chat_id": -75735901261257,
    }
    defaults.update(kwargs)
    return AgentInstance(**defaults)


def _reminder(agent: AgentInstance) -> AgentReminder:
    return AgentReminder(
        id=uuid.uuid4(),
        agent_id=agent.id,
        run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        message_text="новости ИИ",
        status="pending",
        recurrence="hourly",
    )


def test_dispatch_group_without_max_user_id_sends_to_chat():
    agent = _agent(max_user_id=0)
    reminder = _reminder(agent)
    user = MagicMock()
    user.id = agent.user_id

    db = AsyncMock()
    reminder_result = MagicMock()
    reminder_result.scalars.return_value.all.return_value = [reminder]
    agent_result = MagicMock()
    agent_result.scalar_one_or_none.return_value = agent
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    db.execute = AsyncMock(side_effect=[reminder_result, agent_result, user_result])

    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=BotSendResult(ok=True, message_id="mid-1"))

    with (
        patch("app.services.agent.dispatch.append_agent_activity_log", new_callable=AsyncMock),
        patch(
            "app.services.agent.dispatch.probe_max_chat",
            new_callable=AsyncMock,
            return_value={"ok": True, "explanation": "ok"},
        ),
        patch(
            "app.services.agent.dispatch.build_delivery_content",
            new_callable=AsyncMock,
            return_value=DeliveryContent(text="Новости", attachments=[]),
        ),
        patch(
            "app.services.agent.dispatch.schedule_next_recurrence",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.agent.dispatch.dispatch_stagger", new_callable=AsyncMock),
    ):
        count = asyncio.run(dispatch_due_reminders(db, bot=bot, redis_client=AsyncMock()))

    assert count == 1
    bot.send_message.assert_awaited_once()
    call = bot.send_message.await_args
    assert call.kwargs.get("chat_id") == -75735901261257
    assert call.args[0] is None
    assert reminder.status == "sent"


def test_dispatch_dm_requires_max_user_id():
    agent = _agent(
        max_user_id=0,
        max_chat_id=None,
        role=AgentRole.PERSONAL_REMINDER.value,
        config={"reminder_message": "привет", "schedule_text": "через 1 минуту"},
    )
    reminder = _reminder(agent)
    reminder.recurrence = None

    db = AsyncMock()
    reminder_result = MagicMock()
    reminder_result.scalars.return_value.all.return_value = [reminder]
    agent_result = MagicMock()
    agent_result.scalar_one_or_none.return_value = agent
    db.execute = AsyncMock(side_effect=[reminder_result, agent_result])

    bot = AsyncMock()
    with (
        patch("app.services.agent.dispatch.append_agent_activity_log", new_callable=AsyncMock),
        patch("app.services.agent.dispatch.dispatch_stagger", new_callable=AsyncMock),
    ):
        count = asyncio.run(dispatch_due_reminders(db, bot=bot, redis_client=AsyncMock()))

    assert count == 0
    assert reminder.status == "failed"
    assert reminder.last_error == "max_user_id missing"
    bot.send_message.assert_not_called()
