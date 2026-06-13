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
    # Bound chat_id allowed
    assert chat_id_allowed(-100, agent)
    # message_chat_id no longer added to allowlist (security fix #1)
    assert not chat_id_allowed(-200, agent, message_chat_id=-200)
    assert not chat_id_allowed(-999, agent)
    # message_chat_id is NOT in allowed set
    assert -200 not in allowed_chat_ids_for_agent(agent, message_chat_id=-200)


def test_test_send_requires_consent():
    # DRAFT/COLLECTING without awaiting_confirmation — destructive tools blocked
    assert not user_consented_test_send("проверь связь с группой", agent_status="collecting")
    assert not user_consented_test_send("прямо сейчас", agent_status="draft")
    assert not user_consented_test_send("привет", agent_status="collecting")
    assert not user_consented_test_send("", agent_status="active")

    # ACTIVE agents — allowed
    assert user_consented_test_send("что угодно", agent_status="active")

    # awaiting_confirmation — allowed
    assert user_consented_test_send("да", agent_status="collecting", awaiting_confirmation=True)

    # checklist_allow (activation confirmed) — always allowed
    assert user_consented_test_send("", checklist_allow=True)


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


def test_message_chat_id_not_added_to_allowlist():
    """Security regression: chat_id from message text must not be auto-allowed."""
    agent = _agent(max_chat_id=-100)
    # Even with message_chat_id passed, it's not added
    ids = allowed_chat_ids_for_agent(agent, message_chat_id=-99999)
    assert -99999 not in ids
    assert -100 in ids
