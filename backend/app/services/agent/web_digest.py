"""Поиск в интернете + сводка для агента (без search_flow / SSE)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.agent.agent_status import STATUS_SEARCH_FETCH, STATUS_SEARCH_WRITE
from app.services.agent.summarize import summarize_search_sources
from app.services.providers.factory import create_search_provider, resolve_search_provider_id

StatusCallback = Callable[[str], Awaitable[None]]


async def build_web_digest_text(
    db: AsyncSession,
    redis_client,
    user: User,
    *,
    topic: str,
    header: str = "",
    min_chars: int | None = None,
    max_chars: int | None = None,
    on_status: StatusCallback | None = None,
) -> str:
    topic = (topic or "").strip()
    if not topic:
        return "Тема для поиска не задана."

    if on_status:
        await on_status(STATUS_SEARCH_FETCH)
    provider_id = await resolve_search_provider_id(db, redis_client)
    search = create_search_provider(provider_id)
    sources = await search.search(topic, limit=5)
    if on_status:
        await on_status(STATUS_SEARCH_WRITE)
    return await summarize_search_sources(
        db,
        redis_client,
        user,
        topic,
        sources,
        header=header,
        min_chars=min_chars,
        max_chars=max_chars,
    )
