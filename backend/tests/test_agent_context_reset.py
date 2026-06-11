"""Тесты сброса контекста агента."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models.agent import AgentInstance, AgentStatus
from app.models.message import Message, MessageRole
from app.services.agent.context_reset import (
    apply_onboarding_reset,
    history_messages_for_agent,
    is_pure_context_reset_request,
    mark_context_reset,
    user_wants_context_reset,
)


def _msg(role: MessageRole, content: str) -> Message:
    return Message(
        id=uuid4(),
        thread_id=uuid4(),
        role=role,
        content=content,
        created_at=datetime.now(timezone.utc),
    )


def test_user_wants_context_reset():
    assert user_wants_context_reset("сбрось контекст")
    assert user_wants_context_reset("Давай начни заново")
    assert not user_wants_context_reset("отключи агента")
    assert not user_wants_context_reset("напоминай каждый день")


def test_pure_context_reset():
    assert is_pure_context_reset_request("сбрось контекст")
    assert is_pure_context_reset_request("  Начни заново!  ")
    assert not is_pure_context_reset_request(
        "сбрось контекст и настрой напоминание каждый день в 9"
    )


def test_history_trimmed_after_reset():
    agent = AgentInstance(
        thread_id=uuid4(),
        user_id=uuid4(),
        max_user_id=1,
        status=AgentStatus.DRAFT.value,
        config={},
    )
    old_user = _msg(MessageRole.USER, "старая задача")
    old_assistant = _msg(MessageRole.ASSISTANT, "старый ответ")
    reset_user = _msg(MessageRole.USER, "новая задача")
    mark_context_reset(agent, reset_user.id)

    history = history_messages_for_agent(
        [old_user, old_assistant, reset_user],
        agent,
    )
    assert history == [{"role": "user", "text": "новая задача"}]


def test_onboarding_reset_clears_checklist():
    agent = AgentInstance(
        thread_id=uuid4(),
        user_id=uuid4(),
        max_user_id=1,
        status=AgentStatus.COLLECTING.value,
        role="personal_reminder",
        config={
            "checklist": {"role": "personal_reminder", "schedule_text": "каждый день"},
            "schedule_text": "каждый день",
            "knowledge_chunk_count": 3,
        },
    )
    apply_onboarding_reset(agent)
    assert agent.status == AgentStatus.DRAFT.value
    assert agent.role is None
    assert agent.config["checklist"] == {}
    assert agent.config["knowledge_chunk_count"] == 3
