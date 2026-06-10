"""Повторное расписание при ошибке отправки."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.agent import AgentInstance, AgentReminder, AgentRole, AgentStatus
from app.services.agent.content import DeliveryContent
from app.services.agent.dispatch import dispatch_due_reminders
from app.services.bot import BotSendResult


def test_recurring_schedules_next_on_send_failure():
    agent = AgentInstance(
        id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        max_user_id=1,
        status=AgentStatus.ACTIVE.value,
        role=AgentRole.NEWS_DIGEST.value,
        config={"delivery_mode": "group", "search_topic": "AI"},
        max_chat_id=-100,
    )
    reminder = AgentReminder(
        id=uuid.uuid4(),
        agent_id=agent.id,
        run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        message_text="news",
        status="pending",
        recurrence="hourly",
    )
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
    bot.send_message = AsyncMock(return_value=BotSendResult(ok=False, error="HTTP 403"))

    schedule_mock = AsyncMock(return_value=MagicMock())
    with (
        patch("app.services.agent.dispatch.append_agent_activity_log", new_callable=AsyncMock),
        patch(
            "app.services.agent.dispatch.probe_max_chat",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ),
        patch(
            "app.services.agent.dispatch.build_delivery_content",
            new_callable=AsyncMock,
            return_value=DeliveryContent(text="t", attachments=[]),
        ),
        patch("app.services.agent.dispatch.schedule_next_recurrence", schedule_mock),
        patch("app.services.agent.dispatch.dispatch_stagger", new_callable=AsyncMock),
    ):
        count = asyncio.run(dispatch_due_reminders(db, bot=bot, redis_client=AsyncMock()))

    assert count == 0
    assert reminder.status == "failed"
    schedule_mock.assert_awaited_once()
