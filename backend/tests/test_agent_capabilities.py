"""Тесты диалоговой модели возможностей агента."""

from __future__ import annotations

from app.models.agent import AgentRole
from app.services.agent.capabilities import (
    apply_message_hints,
    build_parse_fallback_reply,
    explain_next_step,
    try_local_onboarding_reply,
    user_asks_capabilities,
    user_asks_feasibility,
    user_needs_clarification,
)
from app.services.agent.llm_onboarding import (
    ChecklistState,
    checklist_missing_fields,
    merge_checklist,
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


def test_feasibility_not_capabilities_list():
    q = "Ты можешь сделать напоминание в своем чате?"
    assert user_asks_feasibility(q)
    assert not user_asks_capabilities(q)
    assert try_local_onboarding_reply({}, q) is None


def test_apply_message_hints_extracts_chat_id():
    """apply_message_hints теперь извлекает только chat_id — LLM заполняет остальное."""
    data = apply_message_hints(
        {"role": AgentRole.GROUP_REMINDER.value},
        "ID группы -75602062003657",
    )
    assert data["max_chat_id"] == -75602062003657


def test_apply_message_hints_no_keyword_inference():
    """apply_message_hints не добавляет роль или bot_is_group_admin по ключевым словам."""
    data = apply_message_hints({}, "да, бот админ")
    # Не инферируем из ключевых слов — только LLM
    assert "bot_is_group_admin" not in data
    assert "role" not in data or data.get("role") is None


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


def test_checklist_missing_fields_role():
    cl = ChecklistState()
    missing = checklist_missing_fields(cl)
    assert "role" in missing


def test_merge_checklist_schedule_guard():
    """Слабое расписание не перезаписывает более строгое."""
    current = ChecklistState(
        role=AgentRole.PERSONAL_REMINDER.value,
        schedule_text="каждый день в 16:35",
        timezone="Europe/Moscow",
    )
    patch = ChecklistState(schedule_text="сегодня")
    merged = merge_checklist(current, patch)
    assert merged.schedule_text == "каждый день в 16:35"


def test_merge_checklist_fills_new_fields():
    current = ChecklistState(role=AgentRole.PERSONAL_REMINDER.value)
    patch = ChecklistState(reminder_message="Привет", schedule_text="каждый день в 9:00")
    merged = merge_checklist(current, patch)
    assert merged.reminder_message == "Привет"
    assert merged.schedule_text == "каждый день в 9:00"
