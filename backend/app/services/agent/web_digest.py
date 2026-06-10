"""Поиск в интернете + сводка для агента (без search_flow / SSE)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.agent.summarize import summarize_search_sources
from app.services.providers.factory import create_search_provider, resolve_search_provider_id


async def build_web_digest_text(
    db: AsyncSession,
    redis_client,
    user: User,
    *,
    topic: str,
    header: str = "",
) -> str:
    topic = (topic or "").strip()
    if not topic:
        return "Тема для поиска не задана."

    provider_id = await resolve_search_provider_id(db, redis_client)
    search = create_search_provider(provider_id)
    sources = await search.search(topic, limit=5)
    return await summarize_search_sources(
        db,
        redis_client,
        user,
        topic,
        sources,
        header=header,
    )
