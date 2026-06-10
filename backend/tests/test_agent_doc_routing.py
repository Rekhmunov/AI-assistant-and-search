"""Тесты маршрутизации документов в треде агента."""

from __future__ import annotations

from app.services.agent.doc_routing import (
    agent_message_uses_search_flow,
    agent_thread_allows_search_flow,
    is_agent_setup_query,
)


def test_agent_setup_not_search():
    assert is_agent_setup_query("напоминай каждый день в 9:00")
    assert not agent_message_uses_search_flow("напоминай в 9:00", has_attachments=False)


def test_document_generation_uses_search():
    assert agent_message_uses_search_flow("Создай документ оферту", has_attachments=False)
    assert agent_thread_allows_search_flow(
        "Создай документ оферту",
        has_attachments=False,
        flow_name="chat",
    )


def test_export_prior_uses_search():
    q = "Оформи текст выше в документ"
    assert agent_message_uses_search_flow(q, has_attachments=False)
    assert agent_thread_allows_search_flow(q, has_attachments=False, flow_name="export_chat_document")


def test_legal_doc_chat_uses_search():
    assert agent_message_uses_search_flow("Напиши публичную оферту для сервиса", has_attachments=False)


def test_attachment_analysis_not_setup():
    assert agent_message_uses_search_flow(
        "Проанализируй этот договор",
        has_attachments=True,
    )
    assert not agent_message_uses_search_flow("", has_attachments=True)


def test_faq_upload_stays_agent():
    assert not agent_message_uses_search_flow(
        "Добавь в базу знаний FAQ",
        has_attachments=True,
    )
