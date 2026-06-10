"""Тесты локального распознавания задачи агента."""

from __future__ import annotations

from app.models.agent import AgentRole
from app.services.agent.capabilities import (
    build_parse_fallback_reply,
    try_local_onboarding_reply,
    user_wants_continue,
)
from app.services.agent.intent_hints import (
    infer_checklist_fields,
    infer_role_from_text,
    user_wants_today_run,
)


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


def test_local_skips_feasibility_for_llm():
    text = "Ты можешь сделать напоминание в личке?"
    assert try_local_onboarding_reply({}, text) is None


def test_user_wants_continue():
    assert user_wants_continue("ок")
    assert user_wants_continue("продолжим настройку")


def test_tvoey_gruppe_means_personal_chat():
    role = infer_role_from_text("Ок, давай сделаем напоминание в твоей группе")
    assert role == AgentRole.PERSONAL_REMINDER.value


def test_correction_personal_reminder_with_time_and_text():
    polluted = {
        "role": AgentRole.GROUP_REMINDER.value,
        "reminder_message": "Ты можешь сделать напоминание в своем чате?",
        "schedule_text": None,
    }
    text = 'Нет, напоминание в твоем чате Glosix. В 16:10. Текст напоминания "Привет"'
    data = infer_checklist_fields(text, polluted)
    assert data["role"] == AgentRole.PERSONAL_REMINDER.value
    assert "16:10" in (data.get("schedule_text") or "")
    assert data["reminder_message"] == "Привет"
    assert data["timezone"] == "Europe/Moscow"


def test_daily_schedule_includes_time():
    data = infer_checklist_fields(
        "каждый день в 16:35 в личный чат, текст Привет",
        {},
    )
    assert data["schedule_text"] == "каждый день в 16:35"


def test_bare_today_not_extracted_without_time():
    data = infer_checklist_fields("сегодня", {"role": AgentRole.PERSONAL_REMINDER.value})
    assert "schedule_text" not in data or data.get("schedule_text") is None


def test_today_run_intent():
    assert user_wants_today_run("сегодня сделать")
    data = infer_checklist_fields(
        "сегодня сделать",
        {
            "role": AgentRole.PERSONAL_REMINDER.value,
            "schedule_text": "каждый день в 16:35",
            "reminder_message": "Привет",
        },
    )
    assert data["schedule_text"] == "сегодня в 16:35"


def test_today_run_without_time_is_soon():
    data = infer_checklist_fields(
        "сегодня сделай",
        {
            "role": AgentRole.PERSONAL_REMINDER.value,
            "reminder_message": "Привет",
        },
    )
    assert data["schedule_text"] == "через 2 минуты"


def test_bare_time_gets_default_timezone():
    data = infer_checklist_fields("каждый день в 16:10", {"role": AgentRole.PERSONAL_REMINDER.value})
    assert data["timezone"] == "Europe/Moscow"
