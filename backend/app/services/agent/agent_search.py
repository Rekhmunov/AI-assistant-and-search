"""Полный поиск Glosix для агента (тот же пайплайн, что в search_flow, без SSE)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Plan, User
from app.services.agent.agent_status import STATUS_SEARCH_FETCH, STATUS_SEARCH_WRITE, StatusCallback
from app.services.facts.pipeline import FactPipeline
from app.services.facts.slots import resolve_fact_slots
from app.services.facts.grounding import adjust_grounding_for_retrieval
from app.services.perplexity import PERPLEXITY_PROVIDER_ID, PerplexityProvider
from app.services.providers.factory import resolve_runtime_providers
from app.services.query_router import QueryRouter
from app.services.query_rewriter import QueryRewriter
from app.services.search_flow import sources_to_json
from app.services.search_query import normalize_user_query
from app.services.facts.merge_sources import diversify_sources_by_domain
from app.services.thread_context import build_thread_context, format_sources_for_prompt
from app.services.query_url_memory import lookup_bootstrap_sources

logger = logging.getLogger(__name__)


@dataclass
class AgentSearchResult:
    text: str
    sources: list[dict[str, Any]]
    sources_block: str


def format_sources_for_user(sources: list[dict[str, Any]], *, max_items: int = 8) -> str:
    if not sources:
        return ""
    lines = ["Источники:"]
    for src in sources[:max_items]:
        idx = src.get("index", "?")
        title = (src.get("title") or src.get("domain") or "Источник").strip()
        url = (src.get("url") or "").strip()
        if url:
            lines.append(f"[{idx}] {title} — {url}")
        else:
            lines.append(f"[{idx}] {title}")
    return "\n".join(lines)


def append_sources_to_answer(answer: str, sources: list[dict[str, Any]]) -> str:
    body = (answer or "").strip()
    block = format_sources_for_user(sources)
    if not block:
        return body
    if block in body:
        return body
    return f"{body}\n\n{block}" if body else block


async def run_agent_glosix_search(
    db: AsyncSession,
    redis_client,
    user: User,
    query: str,
    *,
    on_status: StatusCallback | None = None,
) -> AgentSearchResult:
    """Поиск с источниками: Perplexity Sonar или Yandex Search + FactPipeline."""
    topic = normalize_user_query((query or "").strip())
    if not topic:
        return AgentSearchResult(
            text="Тема для поиска не задана.",
            sources=[],
            sources_block="",
        )

    if on_status:
        await on_status(STATUS_SEARCH_FETCH)

    llm, search, _prompt_store, llm_provider_id, _search_provider_id = await resolve_runtime_providers(
        db, redis_client, user=user
    )
    router = QueryRouter()
    thread_ctx = build_thread_context([])
    route = await router.route(topic, thread_ctx, has_attachments=False, user_plan=user.plan)
    route.needs_search = True
    answer_model = route.answer_model
    if user.plan != Plan.PRO:
        answer_model = "lite"

    sources: list = []
    full_answer = ""

    if llm_provider_id == PERPLEXITY_PROVIDER_ID and isinstance(llm, PerplexityProvider):
        async for event in llm.stream_search_answer(
            topic,
            [],
            model=answer_model,  # type: ignore[arg-type]
            prior_sources_block="",
        ):
            if event.sources and not sources:
                sources = diversify_sources_by_domain(
                    event.sources,
                    max_sources=12,
                    howto=route.intent == "howto" or answer_model == "pro",
                    prefer_official_docs=route.intent == "howto",
                )
            if event.text:
                full_answer += event.text
    else:
        rewriter = QueryRewriter(llm)
        rewrite = await rewriter.rewrite(topic, thread_ctx)
        queries = list(rewrite.search_queries or [topic])
        howto = rewrite.intent == "howto"
        if howto:
            answer_model = "pro"
        fact_slots = resolve_fact_slots(rewrite.fact_slots)
        grounding_mode = rewrite.grounding or "hybrid"

        bootstrap_sources, _trace = await lookup_bootstrap_sources(db, topic, *(queries[:2]))
        fact_pipeline = FactPipeline(search, llm)

        def _enhance(q: str) -> str:
            return normalize_user_query(q)[:400]

        pipeline_result = await fact_pipeline.run(
            topic,
            queries,
            enhance_fn=_enhance,
            fact_slots=fact_slots,
            howto=howto,
            answer_model=answer_model,
            bootstrap_sources=bootstrap_sources or None,
            prefer_official_docs=rewrite.prefer_official_docs,
            needs_second_search=rewrite.needs_second_search,
            redis_client=redis_client,
        )
        sources = pipeline_result.sources
        weak_retrieval = bool(
            pipeline_result.retrieval_trace and not pipeline_result.retrieval_trace.get("ok")
        )
        grounding_mode = adjust_grounding_for_retrieval(
            grounding_mode,  # type: ignore[arg-type]
            weak_retrieval=weak_retrieval,
            fact_slots=fact_slots,
        )

        if on_status:
            await on_status(STATUS_SEARCH_WRITE)

        async for chunk in llm.stream_answer(
            topic,
            sources,
            [],
            model=answer_model,
            prior_sources_block=format_sources_for_prompt(thread_ctx.last_assistant_sources),
            fact_pack=pipeline_result.fact_pack,
            intent_howto=howto,
            grounding_mode=grounding_mode,
        ):
            full_answer += chunk

    if on_status and llm_provider_id == PERPLEXITY_PROVIDER_ID:
        await on_status(STATUS_SEARCH_WRITE)

    sources_json = sources_to_json(sources)
    answer = (full_answer or "").strip()
    if not answer and sources_json:
        snippets = [
            f"• {s.get('title', '')} ({s.get('domain', '')})"
            for s in sources_json[:5]
            if s.get("title") or s.get("snippet")
        ]
        answer = f"По теме «{topic}» найдено:\n" + "\n".join(snippets) if snippets else (
            f"По теме «{topic}» свежих результатов не найдено."
        )
    elif not answer:
        answer = f"По теме «{topic}» свежих результатов не найдено."

    sources_block = format_sources_for_user(sources_json)
    return AgentSearchResult(
        text=append_sources_to_answer(answer, sources_json),
        sources=sources_json,
        sources_block=sources_block,
    )
