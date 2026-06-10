import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.agent import AgentInstance, AgentStatus
from app.services.agent.lifecycle import purge_agent_for_thread


def test_purge_agent_for_thread_deletes_instance(monkeypatch):
    thread_id = uuid.uuid4()
    agent = AgentInstance(
        id=uuid.uuid4(),
        thread_id=thread_id,
        user_id=uuid.uuid4(),
        max_user_id=123,
        status=AgentStatus.ACTIVE.value,
    )

    cancel_mock = AsyncMock(return_value=1)
    monkeypatch.setattr("app.services.agent.lifecycle.cancel_reminders_for_agent", cancel_mock)

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = agent
    db.execute.return_value = result

    removed = asyncio.run(purge_agent_for_thread(db, thread_id))

    assert removed is True
    cancel_mock.assert_awaited_once_with(db, agent.id)
    db.delete.assert_called_once_with(agent)
