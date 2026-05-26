"""Переписывание запроса для Yandex Search с учётом истории треда."""

import json
import logging
from dataclasses import dataclass, field

from app.services.facts.slots import normalize_fact_slots
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
    fact_slots: list[str] = field(default_factory=list)


def _parse_rewrite_json(text: str, fallback_query: str) -> RewriteResult | None:
    start = text.find("{")
    if start < 0:
        return None
    data = None
    for end in range(len(text), start, -1):
        if text[end - 1] != "}":
            continue
        try:
            data = json.loads(text[start:end])
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(data, dict):
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
    fact_slots = normalize_fact_slots(data.get("fact_slots"))

    return RewriteResult(
        search_queries=queries[:3],
        needs_clarification=needs_clarification,
        clarification_question=clarification,
        intent=intent,
        reason=reason,
        fact_slots=fact_slots,
    )


class QueryRewriter:
    def __init__(self):
        self.llm = YandexGPTProvider()

    async def rewrite(self, query: str, ctx: ThreadContext) -> RewriteResult:
        query = normalize_user_query(query)
        fallback = query[:400]
        history_text = format_history_compact(ctx.history, max_turns=4)

        prompt = f"""Ты — модуль анализа вопроса перед веб-поиском (как исследователь). Язык: русский.

Вопрос пользователя:
{query[:900]}

История диалога:
{history_text or "(нет)"}

Продолжение диалога: {"да" if ctx.is_continuation else "нет"}

Задачи:
1. Пойми, какие факты нужны пользователю (сами факты, не «где искать»).
2. intent: factual_current | howto | compare_analyze | document | edit_prior | chitchat
3. fact_slots — какие типы структурированных данных нужны (можно несколько или []):
   - fx_rate — только курс валют / обмен (USD, EUR, ЦБ), НЕ «курс на похудение», НЕ «курс обучения»
   - weather_now — погода, температура, осадки в городе
   - company_financial — оборот, выручка, прибыль, ИНН, отчётность компании
   - course_program — программа обучения, похудения, тренировок, «курс по/на …»
   - [] — общие темы (тренды, анализ рынка, новости, определения) без слотов выше
   Примеры: «курс доллара» → ["fx_rate"]; «курс на похудение» → ["course_program"]; «прогноз продаж» → []; «погода в Иваново» → ["weather_now"]
4. search_queries: 1–3 запроса в Yandex со словами, по которым на странице будут цифры/факты (не «где посмотреть», не список сайтов).
   Для fx_rate добавь валюту и «ЦБ»/«котировка»; для weather_now — город, дату, «температура»; для course_program — «программа», «план», «похудение»/тему.
   Если в вопросе «подробный», «детальный», «пошаговый», «план» — запросы на страницы с конкретным планом (недели, меню, тренировки), не общие статьи «советы».
5. «А завтра?» / «а там?» — полный самодостаточный запрос из истории.
6. needs_clarification=true только если без параметра (город, дата, компания) факт недостижим; один короткий вопрос. Не подставляй город по умолчанию.
7. how-to: intent=howto, в search_queries — «официальная документация» / «инструкция».
8. Если needs_clarification=false — минимум один search_queries.

Ответь ТОЛЬКО JSON:
{{"intent": "factual_current", "fact_slots": [], "search_queries": ["..."], "needs_clarification": false, "clarification_question": null, "reason": "..."}}"""

        try:
            raw = await self.llm.complete_text(
                [
                    {"role": "system", "text": "Ты модуль переписывания поисковых запросов. Только JSON."},
                    {"role": "user", "text": prompt},
                ],
                model="lite",
                max_tokens=450,
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
            fact_slots=[],
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
            fact_slots=result.fact_slots,
        )
