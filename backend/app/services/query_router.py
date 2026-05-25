"""Маршрутизация: Search или direct; Lite или Pro."""

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

SEARCH_KEYWORDS = (
    "найди",
    "найти",
    "поиск",
    "поищи",
    "загугли",
    "актуальн",
    "сегодня",
    "сейчас",
    "курс",
    "цена",
    "стоимость",
    "новост",
    "погода",
    "2024",
    "2025",
    "2026",
    "сколько стоит",
    "когда выш",
    "последние данные",
)

DIRECT_KEYWORDS = (
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
    "уточни",
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

PRO_MIN_QUERY_LEN = 120


@dataclass
class RouteDecision:
    needs_search: bool
    search_query: str
    answer_model: AnswerModel
    reason: str


def _has_attachment_marker(query: str) -> bool:
    return "--- Документ:" in query or "[Файлы:" in query


def _rule_route(query: str, ctx: ThreadContext, has_attachments: bool, user_plan: Plan) -> RouteDecision | None:
    q = query.strip().lower()
    normalized = normalize_user_query(query)

    if any(k in q for k in HOWTO_KEYWORDS):
        search_q = enhance_search_query(normalized, for_howto=True)
        return RouteDecision(
            needs_search=True,
            search_query=search_q,
            answer_model="pro",
            reason="rules:howto_guide",
        )

    if has_attachments or _has_attachment_marker(query):
        return RouteDecision(
            needs_search=True,
            search_query=query[:400],
            answer_model="pro",
            reason="rules:attachment",
        )

    if any(k in q for k in SEARCH_KEYWORDS):
        return RouteDecision(
            needs_search=True,
            search_query=query[:400],
            answer_model=_model_from_complexity(query, user_plan),
            reason="rules:search_keyword",
        )

    if ctx.is_continuation and any(k in q for k in DIRECT_KEYWORDS):
        return RouteDecision(
            needs_search=False,
            search_query=query,
            answer_model="lite",
            reason="rules:follow_up_edit",
        )

    if ctx.is_continuation and ctx.prior_search_used and len(q) < 80:
        vague = ("это", "он", "она", "они", "там", "тут", "ещё", "еще", "а ", "ну ")
        if any(q.startswith(v) or q in ("да", "нет", "почему", "зачем") for v in vague):
            return RouteDecision(
                needs_search=False,
                search_query=query,
                answer_model="lite",
                reason="rules:thread_clarification",
            )

    if ctx.is_continuation and not ctx.prior_search_used and len(q) < 60:
        return RouteDecision(
            needs_search=False,
            search_query=query,
            answer_model="lite",
            reason="rules:short_thread_chat",
        )

    if any(k in q for k in PRO_KEYWORDS) or len(query) > PRO_MIN_QUERY_LEN:
        return RouteDecision(
            needs_search=True,
            search_query=query[:400],
            answer_model="pro",
            reason="rules:complex_query",
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
    return RouteDecision(
        needs_search=needs_search,
        search_query=search_query,
        answer_model=answer_model,
        reason=f"classifier:{reason}",
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
            )

        history_text = format_history_compact(ctx.history, max_turns=3)
        prior = "да" if ctx.prior_search_used else "нет"
        prompt = f"""Определи стратегию ответа поискового ассистента.

Текущий вопрос: {query[:800]}
Продолжение диалога: {"да" if ctx.is_continuation else "нет"}
Уже был веб-поиск в треде: {prior}
Есть вложение: {"да" if has_attachments else "нет"}

История:
{history_text or "(нет)"}

Правила:
- needs_search=true если нужны актуальные факты, новости, цены, имена, сравнение компаний, первый вопрос по фактам.
- needs_search=false если переформулировка, сокращение, уточнение по уже данному ответу в истории.
- search_query: короткий запрос для Yandex Search (с контекстом темы из истории).
- answer_model: "pro" для инструкций «как настроить/подключить», сложного анализа, файлов; иначе "lite".
- search_query: для how-to добавь контекст (официальная документация, Yandex Cloud API).

Ответь ТОЛЬКО JSON:
{{"needs_search": true, "search_query": "...", "answer_model": "lite", "reason": "..."}}"""

        try:
            raw = await self.llm.complete_text(
                [
                    {"role": "system", "text": "Ты классификатор запросов. Отвечай только JSON."},
                    {"role": "user", "text": prompt},
                ],
                model="lite",
                max_tokens=200,
                temperature=0.0,
            )
            parsed = _parse_classifier_json(raw, query)
            if parsed:
                return parsed
        except Exception:
            logger.exception("Query classifier failed")

        search_q = enhance_search_query(query, for_howto=is_howto_query(query))
        return RouteDecision(
            needs_search=not ctx.is_continuation or not ctx.prior_search_used,
            search_query=search_q,
            answer_model=_model_from_complexity(query, user_plan),
            reason="fallback:default",
        )
