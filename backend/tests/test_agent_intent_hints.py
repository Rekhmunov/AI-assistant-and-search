"""Тесты локального распознавания задачи агента."""

from __future__ import annotations

from app.models.agent import AgentRole
from app.services.agent.capabilities import (
    build_parse_fallback_reply,
    try_local_onboarding_reply,
    user_wants_continue,
)
from app.services.agent.intent_hints import infer_role_from_text, infer_checklist_fields


def test_infer_personal_reminder():
    role = infer_role_from_text("Напоминай мне каждый день в 9:00 про встречу")
    assert role == AgentRole.PERSONAL_REMINDER.value


def test_infer_dm_assistant_group_support():
    text = "Отвечай в группе на вопросы по FAQ и переводи текст с фото"
    role = infer_role_from_text(text)
    assert role == AgentRole.DM_ASSISTANT.value
    data = infer_checklist_fields(text, {})
    assert data["scope"] == "group"
    assert data["interaction_mode"] == "support"


def test_local_reply_after_capabilities_not_loop():
    reply = build_parse_fallback_reply({}, "продолжим")
    assert "Продолжим настройку с того места" not in reply
    assert "одним сообщением" in reply.lower() or "примеры" in reply.lower()


def test_local_reply_infers_role():
    text = "Напоминай мне каждый день в 9:00 пить воду"
    reply = try_local_onboarding_reply({}, text)
    assert reply is not None
    assert "9" in reply or "расписан" in reply.lower() or "Понял задачу" in reply


def test_user_wants_continue():
    assert user_wants_continue("ок")
    assert user_wants_continue("продолжим настройку")
