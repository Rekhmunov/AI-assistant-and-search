"""Переписывание запроса для Yandex Search с учётом истории треда."""

import json
import logging
from dataclasses import dataclass, field

from app.services.facts.slots import normalize_fact_slots
from app.services.prompts.defaults import REWRITER_SYSTEM, REWRITER_USER
from app.services.search_query import normalize_user_query
from app.services.providers.factory import ChatLLM
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
    def __init__(self, llm: ChatLLM | None = None):
        self.llm = llm or YandexGPTProvider()

    async def rewrite(self, query: str, ctx: ThreadContext) -> RewriteResult:
        query = normalize_user_query(query)
        fallback = query[:400]
        history_text = format_history_compact(ctx.history, max_turns=4)

        template = await self.llm.get_prompt("rewriter_user", REWRITER_USER)
        try:
            user_prompt = template.format(
                query=query[:900],
                history_text=history_text or "(нет)",
                continuation_label="да" if ctx.is_continuation else "нет",
            )
        except KeyError:
            logger.warning("Rewriter prompt template missing placeholders, using default")
            user_prompt = REWRITER_USER.format(
                query=query[:900],
                history_text=history_text or "(нет)",
                continuation_label="да" if ctx.is_continuation else "нет",
            )
        system = await self.llm.get_prompt("rewriter_system", REWRITER_SYSTEM)

        try:
            raw = await self.llm.complete_text(
                [
                    {"role": "system", "text": system},
                    {"role": "user", "text": user_prompt},
                ],
                model="lite",
                max_tokens=450,
                temperature=0.1,
            )
            parsed = _parse_rewrite_json(raw, fallback)
            if parsed:
                return self._ensure_queries(query, parsed)
        except Exception:
            logger.exception("Query rewrite failed")

        return RewriteResult(
            search_queries=[fallback],
            needs_clarification=False,
            clarification_question=None,
            intent="factual_current",
            reason="rewriter_fallback",
            fact_slots=[],
        )

    def _ensure_queries(self, query: str, result: RewriteResult) -> RewriteResult:
        if result.search_queries:
            return result
        return RewriteResult(
            search_queries=[query[:400]],
            needs_clarification=result.needs_clarification,
            clarification_question=result.clarification_question,
            intent=result.intent,
            reason=result.reason,
            fact_slots=result.fact_slots,
        )
