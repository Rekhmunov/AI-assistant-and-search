"""Тесты диалоговой модели возможностей агента."""

from __future__ import annotations

from app.models.agent import AgentRole
from app.services.agent.capabilities import (
    apply_message_hints,
    build_parse_fallback_reply,
    compose_feasibility_reply,
    explain_next_step,
    reply_looks_like_capabilities_template,
    try_local_onboarding_reply,
    user_asks_capabilities,
    user_asks_feasibility,
    user_needs_clarification,
)
from app.services.agent.llm_onboarding import checklist_missing_fields, ChecklistState


def test_user_needs_clarification():
    assert user_needs_clarification("Не совсем понял")
    assert user_needs_clarification("Поясни, пожалуйста")
    assert user_needs_clarification("что дальше делать?")
    assert not user_needs_clarification("каждый день в 9:00")


def test_user_asks_capabilities():
    assert user_asks_capabilities("Что ты умеешь?")
    assert user_asks_capabilities("Какие возможности есть?")
    assert not user_asks_capabilities("напомни мне завтра в 9")


def test_feasibility_not_capabilities_list():
    q = "Ты можешь сделать напоминание в своем чате?"
    assert user_asks_feasibility(q)
    assert not user_asks_capabilities(q)
    assert try_local_onboarding_reply({}, q) is None


def test_feasibility_infers_reminder_role():
    data = apply_message_hints({}, "Ты можешь сделать напоминание в своем чате?")
    assert data.get("role") == AgentRole.PERSONAL_REMINDER.value


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


def test_feasibility_fallback_not_template():
    q = "Ты можешь сделать напоминание в своем чате?"
    reply = build_parse_fallback_reply({}, q)
    assert "Сейчас агент Glosix в MAX умеет" not in reply
    assert "личный чат" in reply.lower() or "да" in reply.lower()


def test_compose_feasibility_with_full_checklist():
    checklist = {
        "role": AgentRole.PERSONAL_REMINDER.value,
        "schedule_text": "16:10",
        "timezone": "Europe/Moscow",
        "reminder_message": "Привет",
    }
    reply = compose_feasibility_reply(checklist, "ты можешь сделать напоминание?")
    assert "Привет" in reply
    assert "16:10" in reply
    assert "часовой пояс" not in reply.lower()


def test_no_timezone_in_missing_fields():
    state = ChecklistState(
        role=AgentRole.PERSONAL_REMINDER.value,
        schedule_text="16:10",
        timezone="Europe/Moscow",
        reminder_message="Привет",
    )
    assert "timezone" not in checklist_missing_fields(state)


def test_explain_next_step_no_timezone_prompt():
    checklist = {
        "role": AgentRole.PERSONAL_REMINDER.value,
        "schedule_text": "16:10",
        "timezone": "Europe/Moscow",
        "reminder_message": None,
    }
    reply = explain_next_step(checklist)
    assert "часовой пояс" not in reply.lower()


def test_detect_capabilities_template():
    tpl = "Сейчас агент Glosix в MAX умеет:\n• присылать уведомления"
    assert reply_looks_like_capabilities_template(tpl)


def test_explain_next_step_helps_when_not_admin():
    checklist = {
        "role": AgentRole.GROUP_REMINDER.value,
        "max_chat_id": -75602062003657,
        "schedule_text": "каждый день в 9:00",
        "timezone": "Europe/Moscow",
        "reminder_message": "Пора на встречу",
        "bot_is_group_admin": False,
    }
    reply = explain_next_step(checklist)
    assert "можно исправить" in reply.lower()
    assert "не поддерживается" not in reply.lower()
