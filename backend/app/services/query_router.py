"""Маршрутизация v2: по умолчанию веб-поиск; direct — узкий whitelist."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings, get_settings
from app.models.user import Plan
from app.services.search_query import enhance_search_query, is_howto_query, normalize_user_query
from app.services.thread_context import ThreadContext, format_history_compact
from app.services.yandex_gpt import YandexGPTProvider

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

POLICY_VERSION = "v2"

EDIT_PRIOR_KEYWORDS = (
    "перефраз",
    "сократи",
    "короче",
    "проще",
    "переведи",
    "перевод",
    "рерайт",
    "исправь текст",
    "объясни ещё раз",
    "подробнее о пункте",
    "что ты имел",
    "резюмируй",
    "итог",
    "вывод",
)

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
    "пошагово",
    "стратег",
)

HOWTO_KEYWORDS = (
    "как настроить",
    "как подключить",
    "как использовать",
    "как создать",
    "как установить",
    "настройка",
    "настроить",
    "подключить",
    "инструкция",
    "пошагов",
    "quickstart",
    "getting started",
)

CHITCHAT_EXACT = frozenset(
    {
        "привет",
        "здравствуй",
        "здравствуйте",
        "hi",
        "hello",
        "спасибо",
        "благодарю",
        "ок",
        "окей",
    }
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


def _is_chitchat(q: str) -> bool:
    stripped = q.strip().lower().rstrip("!?.")
    return len(stripped) < 24 and stripped in CHITCHAT_EXACT


def _is_edit_prior(q: str, ctx: ThreadContext) -> bool:
    return ctx.is_continuation and any(k in q for k in EDIT_PRIOR_KEYWORDS)


def _rule_route(query: str, ctx: ThreadContext, has_attachments: bool, user_plan: Plan) -> RouteDecision | None:
    q = query.strip().lower()
    normalized = normalize_user_query(query)

    if _is_chitchat(q):
        return RouteDecision(
            needs_search=False,
            search_query=query,
            answer_model="lite",
            reason="rules:chitchat",
            intent="chitchat",
        )

    if has_attachments or _has_attachment_marker(query):
        return RouteDecision(
            needs_search=False,
            search_query=query[:400],
            answer_model="pro",
            reason="rules:attachment_direct",
            intent="document",
        )

    if _is_edit_prior(q, ctx):
        return RouteDecision(
            needs_search=False,
            search_query=query,
            answer_model="lite",
            reason="rules:edit_prior",
            intent="edit_prior",
        )

    if any(k in q for k in HOWTO_KEYWORDS) or is_howto_query(normalized):
        search_q = enhance_search_query(normalized, for_howto=True)
        return RouteDecision(
            needs_search=True,
            search_query=search_q,
            answer_model="pro",
            reason="rules:howto_guide",
            intent="howto",
        )

    if any(k in q for k in PRO_KEYWORDS) or len(query) > PRO_MIN_QUERY_LEN:
        return RouteDecision(
            needs_search=True,
            search_query=normalized[:400],
            answer_model="pro",
            reason="rules:compare_analyze",
            intent="compare_analyze",
        )

    return None


def _model_from_complexity(query: str, user_plan: Plan) -> AnswerModel:
    q = query.lower()
    if any(k in q for k in PRO_KEYWORDS) or len(query) > PRO_MIN_QUERY_LEN:
        return "pro"
    if user_plan == Plan.PRO:
        return "lite"
    return "lite"


def _parse_classifier_json(text: str, fallback_query: str) -> RouteDecision | None:
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    needs_search = bool(data.get("needs_search", True))
    search_query = str(data.get("search_query") or fallback_query)[:400]
    model_raw = str(data.get("answer_model", "lite")).lower()
    answer_model: AnswerModel = "pro" if model_raw == "pro" else "lite"
    reason = str(data.get("reason", "classifier"))[:64]
    intent_raw = str(data.get("intent", "factual_current")).lower()
    intent: Intent = "factual_current"
    if intent_raw in ("howto", "document", "edit_prior", "compare_analyze", "chitchat"):
        intent = intent_raw  # type: ignore[assignment]
    if not needs_search and intent == "factual_current":
        intent = "edit_prior"

    return RouteDecision(
        needs_search=needs_search,
        search_query=search_query,
        answer_model=answer_model,
        reason=f"classifier:{reason}",
        intent=intent,
    )


class QueryRouter:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.llm = YandexGPTProvider(self.settings)

    async def route(
        self,
        query: str,
        ctx: ThreadContext,
        has_attachments: bool = False,
        user_plan: Plan = Plan.FREE,
    ) -> RouteDecision:
        query = normalize_user_query(query)
        ruled = _rule_route(query, ctx, has_attachments, user_plan)
        if ruled:
            return ruled

        if not self.settings.yandex_configured:
            return RouteDecision(
                needs_search=True,
                search_query=query[:400],
                answer_model=_model_from_complexity(query, user_plan),
                reason="mock:search",
                intent="factual_current",
            )

        search_q = enhance_search_query(query, for_howto=is_howto_query(query))
        return RouteDecision(
            needs_search=True,
            search_query=search_q,
            answer_model=_model_from_complexity(query, user_plan),
            reason="default:search_v2",
            intent="howto" if is_howto_query(query) else "factual_current",
        )
