"""Переписывание запроса для Yandex Search с учётом истории треда."""

import json
import logging
import re
from dataclasses import dataclass

from app.services.search_query import normalize_user_query
from app.services.thread_context import ThreadContext, format_history_compact
from app.services.yandex_gpt import YandexGPTProvider

logger = logging.getLogger(__name__)


@dataclass
class RewriteResult:
    search_queries: list[str]
    needs_clarification: bool
    clarification_question: str | None
    intent: str
    reason: str


def _parse_rewrite_json(text: str, fallback_query: str) -> RewriteResult | None:
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    raw_queries = data.get("search_queries")
    queries: list[str] = []
    if isinstance(raw_queries, list):
        for item in raw_queries:
            q = str(item).strip()
            if q:
                queries.append(q[:400])
    if not queries:
        sq = str(data.get("search_query") or "").strip()
        if sq:
            queries.append(sq[:400])

    if not queries:
        queries = [fallback_query[:400]]

    needs_clarification = bool(data.get("needs_clarification", False))
    clarification = str(data.get("clarification_question") or "").strip() or None
    intent = str(data.get("intent") or "factual_current")[:32]
    reason = str(data.get("reason") or "rewriter")[:64]

    return RewriteResult(
        search_queries=queries[:2],
        needs_clarification=needs_clarification,
        clarification_question=clarification,
        intent=intent,
        reason=reason,
    )


class QueryRewriter:
    def __init__(self):
        self.llm = YandexGPTProvider()

    async def rewrite(self, query: str, ctx: ThreadContext) -> RewriteResult:
        query = normalize_user_query(query)
        fallback = query[:400]
        history_text = format_history_compact(ctx.history, max_turns=4)

        prompt = f"""Ты готовишь запросы для веб-поиска (Yandex). Язык: русский.

Вопрос пользователя:
{query[:900]}

История диалога:
{history_text or "(нет)"}

Продолжение диалога: {"да" if ctx.is_continuation else "нет"}

Задачи:
1. Понять намерение: factual_current | howto | compare_analyze | document | edit_prior | chitchat
2. Сформировать 1–2 самодостаточных поисковых запроса (с городом, датой, продуктом из контекста).
3. «А в среду?» / «а там?» — восстанови полный запрос из истории.
4. Если без ключевого параметра (город, дата, объект) факт невозможно искать — needs_clarification=true и один короткий вопрос. Не подставляй город по умолчанию.
5. search_queries — запросы на страницы с фактами (цифры, даты), не «где посмотреть» / «список сайтов».
6. Для how-to добавь «официальная документация» или «инструкция» где уместно.
7. Всегда возвращай хотя бы один search_queries, если needs_clarification=false.

Ответь ТОЛЬКО JSON:
{{"intent": "factual_current", "search_queries": ["..."], "needs_clarification": false, "clarification_question": null, "reason": "..."}}"""

        try:
            raw = await self.llm.complete_text(
                [
                    {"role": "system", "text": "Ты модуль переписывания поисковых запросов. Только JSON."},
                    {"role": "user", "text": prompt},
                ],
                model="lite",
                max_tokens=350,
                temperature=0.1,
            )
            parsed = _parse_rewrite_json(raw, fallback)
            if parsed:
                return self._ensure_queries(query, parsed)
        except Exception:
            logger.exception("Query rewriter failed")

        return RewriteResult(
            search_queries=[fallback],
            needs_clarification=False,
            clarification_question=None,
            intent="factual_current",
            reason="rewriter:fallback",
        )

    def _ensure_queries(self, user_query: str, result: RewriteResult) -> RewriteResult:
        if result.needs_clarification:
            return result
        if result.search_queries:
            return result
        return RewriteResult(
            search_queries=[user_query[:400]],
            needs_clarification=False,
            clarification_question=None,
            intent=result.intent,
            reason=result.reason,
        )
