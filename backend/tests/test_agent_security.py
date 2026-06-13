import uuid

from app.models.agent import AgentInstance, AgentStatus
from app.models.user import User
from app.services.agent.agent_security import (
    AgentSecurityError,
    allowed_chat_ids_for_agent,
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
    assert chat_id_allowed(-100, agent)
    assert chat_id_allowed(-200, agent, message_chat_id=-200)
    assert not chat_id_allowed(-999, agent)
    assert -200 in allowed_chat_ids_for_agent(agent, message_chat_id=-200)


def test_test_send_requires_consent():
    # Any non-empty user text in a Glosix agent thread is considered explicit interaction.
    # Real protection is the chat_id binding (validate_tool_call), not keyword matching.
    assert user_consented_test_send("проверь связь с группой")
    assert user_consented_test_send("прямо сейчас")
    assert user_consented_test_send("привет")
    assert not user_consented_test_send("")
    assert not user_consented_test_send("   ")


def test_max_send_message_allowed_with_consent():
    agent = _agent()
    user = User(id=agent.user_id, max_user_id=1)
    payload = validate_tool_call(
        "max_send_message",
        {"chat_id": -100, "text": "тест"},
        agent=agent,
        user=user,
        message_chat_id=None,
        allow_test_send=True,
    )
    assert payload["text"] == "тест"


def test_forbidden_tool_rejected():
    agent = _agent()
    user = User(id=agent.user_id, max_user_id=1)
    try:
        validate_tool_call(
            "shell_exec",
            {"cmd": "rm -rf /"},
            agent=agent,
            user=user,
            message_chat_id=None,
            allow_test_send=True,
        )
        assert False, "expected AgentSecurityError"
    except AgentSecurityError as exc:
        assert "tool_not_allowed" in str(exc)


def test_store_agent_record_validation():
    agent = _agent()
    user = User(id=agent.user_id, max_user_id=1)
    payload = validate_tool_call(
        "store_agent_record",
        {"table": "expenses", "data": {"amount": 100, "category": "Аренда"}},
        agent=agent,
        user=user,
        message_chat_id=None,
        allow_test_send=False,
    )
    assert payload["table"] == "expenses"
    assert payload["data"]["amount"] == 100
