"""Сбор debug_trace для админки (отладка Yandex Search / GPT)."""

from typing import Any

from app.core.config import Settings, get_settings
from app.services.llm_provider import SearchSource
from app.services.facts.models import FactPack
from app.services.query_router import RouteDecision
from app.services.providers.factory import ChatLLM, llm_model_label

_TRACE_TEXT_LIMIT = 12_000


def _clip(text: str, limit: int = _TRACE_TEXT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


async def build_gpt_messages_preview(
    llm: ChatLLM,
    *,
    llm_query: str,
    sources: list[SearchSource],
    history: list[tuple[str, str]],
    prior_sources_block: str,
    needs_search: bool,
    model: str,
    hint_clarify: str | None = None,
    fact_pack: FactPack | None = None,
) -> list[dict[str, str]]:
    if needs_search:
        raw = await llm._build_messages_search(
            llm_query,
            sources,
            history,
            prior_sources_block,
            hint_clarify=hint_clarify,
            fact_pack=fact_pack,
        )
    else:
        raw = await llm._build_messages_direct(llm_query, history, prior_sources_block)
    return [{"role": m["role"], "text": _clip(m["text"])} for m in raw]


def build_debug_trace(
    *,
    llm: ChatLLM,
    llm_provider_id: str,
    display_content: str,
    llm_query: str,
    route: RouteDecision,
    search_query_sent: str | None,
    sources: list[SearchSource],
    sources_json: list[dict],
    needs_search: bool,
    answer_model: str,
    gpt_messages_preview: list[dict[str, str]],
    rewrite: dict[str, Any] | None = None,
    search_attempts: list[dict[str, Any]] | None = None,
    retrieval: dict[str, Any] | None = None,
    fact_pack: dict[str, Any] | None = None,
    page_cache: dict[str, Any] | None = None,
    query_url_memory: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    s = settings or get_settings()
    return {
        "user_display": _clip(display_content, 4000),
        "llm_query": _clip(llm_query, 8000),
        "route": {
            "needs_search": route.needs_search,
            "search_query": route.search_query,
            "answer_model": route.answer_model,
            "reason": route.reason,
            "intent": route.intent,
            "policy_version": route.policy_version,
        },
        "query_rewrite": rewrite,
        "yandex_search": None
        if not needs_search
        else {
            "query_sent": search_query_sent,
            "attempts": search_attempts or [],
            "retrieval": retrieval,
            "sources_count": len(sources),
            "sources": sources_json,
        },
        "fact_pack": fact_pack,
        "page_cache": page_cache,
        "query_url_memory": query_url_memory,
        "llm_provider": llm_provider_id,
        "yandex_gpt": {
            "mode": "search" if needs_search else "direct",
            "model": answer_model,
            "model_uri": llm_model_label(llm, answer_model),
            "messages_to_api": gpt_messages_preview,
        },
    }
