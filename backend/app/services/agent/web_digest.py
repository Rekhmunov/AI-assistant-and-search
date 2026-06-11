"""Поиск в интернете для агента — полный пайплайн Glosix с источниками."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.agent.agent_search import run_agent_glosix_search
from app.services.agent.summarize import summarize_search_sources
from app.services.llm_provider import SearchSource

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

    result = await run_agent_glosix_search(
        db,
        redis_client,
        user,
        topic,
        on_status=on_status,
    )

    if min_chars and max_chars and max_chars >= min_chars and result.sources:
        sources = [
            SearchSource(
                index=int(s.get("index") or i + 1),
                url=str(s.get("url") or ""),
                title=str(s.get("title") or ""),
                snippet=str(s.get("snippet") or ""),
                domain=str(s.get("domain") or ""),
            )
            for i, s in enumerate(result.sources)
        ]
        body = await summarize_search_sources(
            db,
            redis_client,
            user,
            topic,
            sources,
            header="",
            min_chars=min_chars,
            max_chars=max_chars,
        )
        if result.sources_block and result.sources_block not in body:
            body = f"{body.strip()}\n\n{result.sources_block}"
    else:
        body = result.text

    body = (body or "").strip()
    if header.strip():
        return f"{header.strip()}\n\n{body}"
    return body
