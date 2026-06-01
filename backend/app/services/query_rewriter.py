"""Search Planner v2: Lite LLM планирует поиск до Yandex Search."""

import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from app.services.facts.slots import normalize_fact_slots
from app.services.facts.grounding import GroundingMode, normalize_grounding, resolve_grounding_mode
from app.services.prompts.defaults import REWRITER_SYSTEM, REWRITER_USER
from app.services.search_query import normalize_user_query
from app.services.providers.factory import ChatLLM
from app.services.thread_context import ThreadContext, format_history_compact
from app.services.yandex_gpt import YandexGPTProvider

logger = logging.getLogger(__name__)

TopicType = Literal["general", "place", "product_tech", "numeric", "program"]

_VALID_TOPIC_TYPES: frozenset[str] = frozenset(
    {"general", "place", "product_tech", "numeric", "program"}
)


@dataclass
class RewriteResult:
    search_queries: list[str]
    needs_clarification: bool
    clarification_question: str | None
    intent: str
    reason: str
    fact_slots: list[str] = field(default_factory=list)
    grounding: GroundingMode | None = None
    topic_type: TopicType = "general"
    needs_second_search: bool = False
    prefer_official_docs: bool = False


def normalize_topic_type(raw: object) -> TopicType:
    t = str(raw or "general").strip().lower()[:32]
    if t in _VALID_TOPIC_TYPES:
        return t  # type: ignore[return-value]
    return "general"


def infer_prefer_official_docs(
    *,
    topic_type: TopicType,
    intent: str,
    fact_slots: list[str],
    explicit: bool | None,
) -> bool:
    if explicit is not None:
        return explicit
    if topic_type == "product_tech":
        return True
    if intent == "howto" and topic_type in ("product_tech", "general"):
        return topic_type == "product_tech"
    return False


def infer_needs_second_search(
    *,
    intent: str,
    topic_type: TopicType,
    explicit: bool | None,
    query_count: int,
) -> bool:
    if explicit is not None:
        return explicit
    if intent in ("compare_analyze",):
        return True
    if topic_type == "program" and query_count > 1:
        return True
    return False


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
    grounding = normalize_grounding(data.get("grounding"))
    topic_type = normalize_topic_type(data.get("topic_type"))

    prefer_raw = data.get("prefer_official_docs")
    prefer_explicit = bool(prefer_raw) if prefer_raw is not None else None
    prefer_official_docs = infer_prefer_official_docs(
        topic_type=topic_type,
        intent=intent,
        fact_slots=fact_slots,
        explicit=prefer_explicit,
    )

    second_raw = data.get("needs_second_search")
    second_explicit = bool(second_raw) if second_raw is not None else None
    needs_second_search = infer_needs_second_search(
        intent=intent,
        topic_type=topic_type,
        explicit=second_explicit,
        query_count=len(queries),
    )

    return RewriteResult(
        search_queries=queries[:3],
        needs_clarification=needs_clarification,
        clarification_question=clarification,
        intent=intent,
        reason=reason,
        fact_slots=fact_slots,
        grounding=grounding,
        topic_type=topic_type,
        needs_second_search=needs_second_search,
        prefer_official_docs=prefer_official_docs,
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
        except (KeyError, ValueError):
            logger.warning("Rewriter prompt template invalid, using default")
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
                max_tokens=550,
                temperature=0.1,
            )
            parsed = _parse_rewrite_json(raw, fallback)
            if parsed:
                result = self._ensure_queries(query, parsed)
                result.grounding = resolve_grounding_mode(
                    fact_slots=result.fact_slots,
                    intent=result.intent,
                    rewriter_grounding=result.grounding,
                    query=query,
                )
                return result
        except Exception:
            logger.exception("Query rewrite failed")

        return self._fallback_result(query)

    def _fallback_result(self, query: str) -> RewriteResult:
        return RewriteResult(
            search_queries=[query[:400]],
            needs_clarification=False,
            clarification_question=None,
            intent="factual_current",
            reason="rewriter_fallback",
            fact_slots=[],
            topic_type="general",
            needs_second_search=False,
            prefer_official_docs=False,
            grounding=resolve_grounding_mode(
                fact_slots=[],
                intent="factual_current",
                query=query,
            ),
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
            grounding=result.grounding,
            topic_type=result.topic_type,
            needs_second_search=result.needs_second_search,
            prefer_official_docs=result.prefer_official_docs,
        )
