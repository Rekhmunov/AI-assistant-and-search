"""Маршрутизация: нормализация запроса и формирование RouteDecision.

Смысловая маршрутизация (needs_search, intent, answer_model) полностью
делегирована llm_flow_router. Этот модуль отвечает только за нормализацию
поискового запроса и предоставляет совместимый RouteDecision.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings, get_settings
from app.models.user import Plan
from app.services.search_query import normalize_user_query
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

POLICY_VERSION = "v7.0"


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
        """
        Возвращает базовый RouteDecision.
        needs_search, intent и answer_model переопределяются в search_flow.py
        значениями из llm_flow_router (LlmFlowDecision).
        Здесь только нормализуем поисковый запрос.
        """
        normalized = normalize_user_query(query)

        # Документ во вложении — явный признак intent=document
        intent: Intent = "document" if (has_attachments or _has_attachment_marker(query)) else "factual_current"

        return RouteDecision(
            needs_search=True,
            search_query=normalized[:400],
            answer_model="pro",
            reason="llm_flow_router",
            intent=intent,
            policy_version=POLICY_VERSION,
        )
