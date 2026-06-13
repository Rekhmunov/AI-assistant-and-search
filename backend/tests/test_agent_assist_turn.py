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
    # apply_message_hints больше не инферирует роль — только LLM
    assert data.get("role") is None


def test_admin_check_with_link_extracts_chat_id():
    text = f"Вот группа {GROUP_URL}\nПроверь, ты там админ?"
    assert is_assist_turn(text)
    data = infer_checklist_fields(text, {})
    # infer_checklist_fields извлекает только chat_id
    assert data.get("max_chat_id") == -75602062003657


def test_user_rejection_does_not_clear_role():
    """user_corrects_understanding обнаруживает коррекцию, но apply_message_hints
    больше не очищает роль по ключевым словам — LLM управляет чеклистом."""
    text = "Я тебе задачу никакую не давал, почему ты решил, что это твоя задача?"
    assert user_corrects_understanding(text)
    # apply_message_hints только извлекает chat_id если есть — не трогает role
    data = apply_message_hints(
        {"role": AgentRole.DM_ASSISTANT.value, "scope": "group"},
        text,
    )
    # Роль остаётся нетронутой — LLM её обнулит если нужно
    assert data.get("role") == AgentRole.DM_ASSISTANT.value


def test_apply_message_hints_only_extracts_chat_id():
    """apply_message_hints теперь минималистичен — только chat_id."""
    text = "Напоминай мне каждый день в 9 про встречу в личке MAX"
    data = apply_message_hints({}, text)
    # Нет chat_id в тексте — ничего не добавляем
    assert data.get("role") is None
    assert data.get("schedule_text") is None
