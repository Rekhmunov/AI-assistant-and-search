import uuid

from app.models.agent import AgentInstance, AgentStatus
from app.models.user import User
from app.services.agent.agent_security import (
    AgentSecurityError,
    chat_id_allowed,
    validate_tool_call,
    user_consented_test_send,
)


def _agent(**kwargs) -> AgentInstance:
    defaults = {
        "id": uuid.uuid4(),
        "thread_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "max_user_id": 1,
        "status": AgentStatus.COLLECTING.value,
        "max_chat_id": -100,
        "config": {},
        "instruction_text": "",
    }
    defaults.update(kwargs)
    return AgentInstance(**defaults)


def test_chat_id_allowed_for_agent():
    agent = _agent(max_chat_id=-100)
    user = User(id=agent.user_id, max_user_id=1)
    assert chat_id_allowed(-100, agent, user, set())
    assert not chat_id_allowed(-999, agent, user, set())


def test_test_send_requires_consent():
    assert user_consented_test_send("проверь связь с группой")
    assert not user_consented_test_send("привет")


def test_forbidden_tool_rejected():
    agent = _agent()
    user = User(id=agent.user_id, max_user_id=1)
    try:
        validate_tool_call(
            "max_send_message",
            {"chat_id": -100, "text": "hack"},
            agent=agent,
            user=user,
            allowed_chats=set(),
            allow_test_send=True,
        )
        assert False, "expected AgentSecurityError"
    except AgentSecurityError as exc:
        assert "tool_not_allowed" in str(exc)
