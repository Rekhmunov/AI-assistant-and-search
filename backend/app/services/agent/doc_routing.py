"""Когда сообщение в треде агента идёт в поисковый SSE-поток (документы), а не в onboarding."""

from __future__ import annotations

import re

from app.services.agent.capabilities import user_wants_immediate_lookup
from app.services.doc_gen_context import refers_to_prior_answer
from app.services.doc_gen_routing import wants_document_generation
from app.services.document_answer_enforce import is_legal_document_request

_AGENT_SETUP_RE = re.compile(
    r"(?:напомин|уведом|агент|max\b|бот\b|групп|модерац|faq|база\s+знан|"
    r"поддержк|расписан|часовой\s+пояс|запусти|подтверж)",
    re.I,
)

_DOC_CHAT_RE = re.compile(
    r"(?i)(?:"
    r"(?:напиши|создай|составь|сформируй|подготовь|сделай|разработай)"
    r"(?:\s+\S+){0,6}\s+(?:оферт|договор|соглашен|заявлен|политик|регламент|устав|приказ|документ)"
    r"|(?:оферт|договор|заявлен|политик)\s+(?:для|на|по)\b"
    r")",
)


def is_agent_setup_query(query: str) -> bool:
    low = (query or "").strip().lower()
    if not low:
        return False
    return bool(_AGENT_SETUP_RE.search(low))


def agent_message_uses_search_flow(query: str, *, has_attachments: bool) -> bool:
    """
    Поиск Glosix (SSE): документы, актуальные факты из интернета, анализ файлов.
    Настройка MAX-агента — через /api/agent/.../messages.
    """
    text = (query or "").strip()
    if has_attachments:
        if not text or text.startswith("[Загружено документов"):
            return False
        return not is_agent_setup_query(text)

    if user_wants_immediate_lookup(text) and not is_agent_setup_query(text):
        return True

    if wants_document_generation(text):
        return True
    if refers_to_prior_answer(text):
        return True
    if is_legal_document_request(text):
        return True
    if _DOC_CHAT_RE.search(text):
        return True
    return False


def agent_thread_allows_search_flow(
    query: str,
    *,
    has_attachments: bool,
    flow_name: str,
) -> bool:
    if not agent_message_uses_search_flow(query, has_attachments=has_attachments):
        return False
    if flow_name == "export_chat_document":
        return True
    if flow_name in {"chat", "search_rag"}:
        return True
    if has_attachments and flow_name in {"chat", "search_rag", "export_chat_document"}:
        return True
    return (
        user_wants_immediate_lookup(query)
        or wants_document_generation(query)
        or refers_to_prior_answer(query)
    )
