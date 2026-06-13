"""Тесты распознавания намерений агента."""

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
    user_wants_immediate_run,
    user_wants_today_run,
)


def test_infer_personal_reminder():
    role = infer_role_from_text("Напоминай мне каждый день в 9:00 про встречу")
    assert role == AgentRole.PERSONAL_REMINDER.value


def test_infer_dm_assistant():
    role = infer_role_from_text("Отвечай на вопросы в группе как поддержка")
    assert role == AgentRole.DM_ASSISTANT.value


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


def test_infer_checklist_extracts_chat_id():
    """infer_checklist_fields теперь извлекает только chat_id — LLM заполняет остальное."""
    text = "Напиши в группу https://web.max.ru/-75602062003657 привет"
    data = infer_checklist_fields(text, {})
    assert data["max_chat_id"] == -75602062003657


def test_infer_checklist_no_role_injection():
    """infer_checklist_fields больше не проставляет role — только LLM."""
    text = "Публикуй новости про ИИ каждый час"
    data = infer_checklist_fields(text, {})
    # Только chat_id если есть, роль не трогаем
    assert "role" not in data or data.get("role") is None


def test_infer_checklist_preserves_existing_chat_id():
    """Если chat_id нет в тексте — не трогаем существующий."""
    base = {"max_chat_id": -12345}
    data = infer_checklist_fields("напомни мне про встречу", base)
    assert data["max_chat_id"] == -12345


def test_user_wants_immediate_run():
    assert user_wants_immediate_run("разово")
    assert user_wants_immediate_run("один раз")
    assert not user_wants_immediate_run("каждый день")


def test_user_wants_today_run():
    assert user_wants_today_run("сегодня сделай")
    assert not user_wants_today_run("завтра")


def test_group_post_chat_id_extracted():
    """chat_id из ссылки извлекается корректно."""
    text = "Напиши в группу https://web.max.ru/-75602062003657 Привет"
    data = infer_checklist_fields(text, {})
    assert data["max_chat_id"] == -75602062003657
