"""Тесты режимов взаимодействия агента."""

from __future__ import annotations

from app.models.agent import AgentInstance, AgentRole, AgentStatus
from app.services.agent.interaction import (
    interaction_mode,
    message_addresses_agent,
    should_handle_dm,
    should_handle_group,
)
from app.services.agent.knowledge import split_knowledge_text


def _agent(**kwargs) -> AgentInstance:
    defaults = {
        "role": AgentRole.DM_ASSISTANT.value,
        "status": AgentStatus.ACTIVE.value,
        "config": {},
        "max_chat_id": 100,
    }
    defaults.update(kwargs)
    agent = AgentInstance(
        thread_id=__import__("uuid").uuid4(),
        user_id=__import__("uuid").uuid4(),
        max_user_id=1,
    )
    for k, v in defaults.items():
        setattr(agent, k, v)
    return agent


def test_split_knowledge_text():
    text = "абв " * 500
    chunks = split_knowledge_text(text, chunk_size=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_support_mode_handles_any_text():
    agent = _agent(config={"interaction_mode": "support", "scope": "dm"})
    assert should_handle_dm(agent, text="привет", command=None, has_images=False) is True


def test_command_mode_requires_command():
    agent = _agent(config={"interaction_mode": "command", "dm_command": "news", "scope": "dm"})
    assert should_handle_dm(agent, text="привет", command="news", has_images=False) is False
    assert should_handle_dm(agent, text="/news", command="news", has_images=False) is True


def test_group_support_with_image():
    agent = _agent(config={"interaction_mode": "support", "scope": "group"}, max_chat_id=42)
    assert should_handle_group(
        agent,
        text="",
        command=None,
        has_images=True,
        chat_id=42,
    )


def test_message_addresses_agent():
    assert message_addresses_agent("/news сегодня", "news") is True
    assert message_addresses_agent("привет бот", None) is True


def test_interaction_mode_default():
    assert interaction_mode({}) == "command"
