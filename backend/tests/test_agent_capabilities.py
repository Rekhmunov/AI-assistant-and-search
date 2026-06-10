"""Тесты диалоговой модели возможностей агента."""

from __future__ import annotations

from app.models.agent import AgentRole
from app.services.agent.capabilities import (
    apply_message_hints,
    build_parse_fallback_reply,
    explain_next_step,
    user_asks_capabilities,
    user_needs_clarification,
)


def test_user_needs_clarification():
    assert user_needs_clarification("Не совсем понял")
    assert user_needs_clarification("Поясни, пожалуйста")
    assert user_needs_clarification("что дальше делать?")
    assert not user_needs_clarification("каждый день в 9:00")


def test_user_asks_capabilities():
    assert user_asks_capabilities("Что ты умеешь?")
    assert user_asks_capabilities("Какие возможности есть?")
    assert not user_asks_capabilities("напомни мне завтра в 9")


def test_apply_message_hints_extracts_chat_id():
    data = apply_message_hints(
        {"role": AgentRole.GROUP_REMINDER.value},
        "ID группы -75602062003657",
    )
    assert data["max_chat_id"] == -75602062003657


def test_apply_message_hints_admin_yes():
    data = apply_message_hints(
        {"role": AgentRole.GROUP_REMINDER.value},
        "да, бот админ",
    )
    assert data["bot_is_group_admin"] is True


def test_clarification_fallback_keeps_context():
    checklist = {
        "role": AgentRole.GROUP_REMINDER.value,
        "max_chat_id": -75602062003657,
        "schedule_text": None,
        "timezone": None,
        "reminder_message": None,
    }
    reply = build_parse_fallback_reply(checklist, "Не совсем понял")
    assert "Поясню проще" in reply
    assert "75602062003657" in reply
    assert "когда" in reply.lower() or "расписан" in reply.lower()
    assert "напоминание в личный чат или работу с группой" not in reply


def test_explain_next_step_group_admin():
    checklist = {
        "role": AgentRole.GROUP_REMINDER.value,
        "max_chat_id": -75602062003657,
        "schedule_text": "каждый день в 9:00",
        "timezone": "Europe/Moscow",
        "reminder_message": "Пора на встречу",
        "bot_is_group_admin": None,
    }
    reply = explain_next_step(checklist)
    assert "администратор" in reply.lower()
