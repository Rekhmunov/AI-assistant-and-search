"""Тесты режима помощника: диагностика без автонастройки агента."""

from __future__ import annotations

from app.models.agent import AgentRole
from app.services.agent.capabilities import apply_message_hints
from app.services.agent.intent_hints import infer_checklist_fields, user_corrects_understanding
from app.services.agent.operational import is_assist_turn, is_bare_max_link_message, user_wants_admin_check

GROUP_URL = "https://web.max.ru/-75602062003657"


def test_admin_list_question_is_assist():
    text = "А ты можешь проверить чаты, в которых ты сейчас админ?"
    assert user_wants_admin_check(text)
    assert is_assist_turn(text)


def test_bare_group_link_is_assist_not_setup():
    assert is_bare_max_link_message(GROUP_URL)
    assert is_assist_turn(GROUP_URL)
    data = apply_message_hints({}, GROUP_URL)
    assert data.get("max_chat_id") == -75602062003657
    assert data.get("role") is None


def test_admin_check_with_link_is_assist():
    text = f"Вот группа {GROUP_URL}\nПроверь, ты там админ?"
    assert is_assist_turn(text)
    data = infer_checklist_fields(text, {"role": AgentRole.DM_ASSISTANT.value})
    assert data.get("role") is None
    assert data.get("max_chat_id") == -75602062003657


def test_user_rejection_clears_role():
    text = "Я тебе задачу никакую не давал, почему ты решил, что это твоя задача?"
    assert user_corrects_understanding(text)
    data = apply_message_hints(
        {"role": AgentRole.DM_ASSISTANT.value, "scope": "group", "interaction_mode": "command"},
        text,
    )
    assert data.get("role") is None
    assert data.get("scope") is None


def test_setup_task_still_infers_role():
    text = "Напоминай мне каждый день в 9 про встречу в личке MAX"
    assert not is_assist_turn(text)
    data = apply_message_hints({}, text)
    assert data.get("role") == AgentRole.PERSONAL_REMINDER.value
