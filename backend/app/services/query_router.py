"""Маршрутизация v6.1: слой 0 — только LLM или поиск + RAG."""

import logging
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings, get_settings
from app.models.user import Plan
from app.services.search_query import (
    enhance_search_query,
    is_chitchat_query,
    is_howto_query,
    is_meta_assistant_query,
    normalize_user_query,
)
from app.services.thread_context import ThreadContext

logger = logging.getLogger(__name__)

AnswerModel = Literal["lite", "pro"]
Intent = Literal[
    "factual_current",
    "howto",
    "document",
    "edit_prior",
    "compare_analyze",
    "chitchat",
]

POLICY_VERSION = "v6.1"

EDIT_PRIOR_KEYWORDS = (
    "перефраз",
    "сократи",
    "короче",
    "проще",
    "переведи",
    "перевод",
    "рерайт",
    "исправь текст",
    "резюмируй",
    "итог",
    "вывод",
    "перепиши",
    "отредактируй",
    "убери лишнее",
)

EDIT_PRIOR_MAX_LEN = 120

PRO_KEYWORDS = (
    "сравни",
    "сравнение",
    "проанализируй",
    "анализ",
    "таблиц",
    "за и против",
    "плюсы и минусы",
    "подробный отчёт",
    "детальный разбор",
)

PRO_MIN_QUERY_LEN = 120


@dataclass
class RouteDecision:
    needs_search: bool
    search_query: str
    answer_model: AnswerModel
    reason: str
    intent: Intent = "factual_current"
    policy_version: str = POLICY_VERSION


def _has_attachment_marker(query: str) -> bool:
    return "--- Документ:" in query or "[Файлы:" in query


def is_edit_prior_without_search(query: str, ctx: ThreadContext) -> bool:
    """
    Правка прошлого ответа в треде — без нового веб-поиска.
    Не срабатывает на длинных запросах с новой темой или how-to.
    """
    if not ctx.is_continuation or not ctx.history:
        return False
    if _has_attachment_marker(query):
        return False
    q = query.strip()
    if len(q) > EDIT_PRIOR_MAX_LEN:
        return False
    lower = q.lower()
    if not any(k in lower for k in EDIT_PRIOR_KEYWORDS):
        return False
    if is_howto_query(q) or is_chitchat_query(q) or is_meta_assistant_query(q):
        return False
    new_topic_markers = (
        "найди",
        "поищи",
        "курс",
        "цена",
        "погода",
        "новост",
        "сколько стоит",
        "актуальн",
    )
    if any(m in lower for m in new_topic_markers):
        return False
    return True


def _detect_intent(
    query: str,
    ctx: ThreadContext,
    has_attachments: bool,
) -> Intent:
    q = query.lower()
    if has_attachments or _has_attachment_marker(query):
        return "document"
    if ctx.is_continuation and any(k in q for k in EDIT_PRIOR_KEYWORDS):
        return "edit_prior"
    if is_howto_query(query):
        return "howto"
    if any(k in q for k in PRO_KEYWORDS) or len(query) > PRO_MIN_QUERY_LEN:
        return "compare_analyze"
    return "factual_current"


def _model_for_intent(intent: Intent, query: str, user_plan: Plan) -> AnswerModel:
    if intent in ("howto", "document", "compare_analyze"):
        return "pro"
    if any(k in query.lower() for k in PRO_KEYWORDS) or len(query) > PRO_MIN_QUERY_LEN:
        return "pro"
    return "lite"


def _llm_only_route(
    query: str,
    *,
    reason: str,
    intent: Intent,
) -> RouteDecision:
    return RouteDecision(
        needs_search=False,
        search_query=query,
        answer_model="lite",
        reason=reason,
        intent=intent,
    )


def _build_search_route(
    query: str,
    ctx: ThreadContext,
    has_attachments: bool,
    user_plan: Plan,
    *,
    reason: str,
) -> RouteDecision:
    normalized = normalize_user_query(query)
    intent = _detect_intent(normalized, ctx, has_attachments)
    search_q = enhance_search_query(
        normalized,
        for_howto=intent == "howto",
    )
    return RouteDecision(
        needs_search=True,
        search_query=search_q,
        answer_model=_model_for_intent(intent, normalized, user_plan),
        reason=reason,
        intent=intent,
    )


class QueryRouter:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def route(
        self,
        query: str,
        ctx: ThreadContext,
        has_attachments: bool = False,
        user_plan: Plan = Plan.FREE,
    ) -> RouteDecision:
        query = normalize_user_query(query)

        if is_chitchat_query(query):
            return _llm_only_route(query, reason="rules:chitchat", intent="chitchat")

        if is_meta_assistant_query(query):
            return _llm_only_route(query, reason="rules:meta_assistant", intent="chitchat")

        if is_edit_prior_without_search(query, ctx):
            return _llm_only_route(query, reason="rules:edit_prior", intent="edit_prior")

        return _build_search_route(
            query,
            ctx,
            has_attachments,
            user_plan,
            reason="search_rag:v6.1",
        )
