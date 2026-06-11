"""Память треда: поиск по истории и обновление summary."""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from app.models.message import Message, MessageRole
from app.services.agent.agent_spec import AgentSpec, append_fact, load_agent_spec, save_agent_spec

logger = logging.getLogger(__name__)

SEARCH_LIMIT = 80
SNIPPET_LEN = 600


def _tokenize(query: str) -> set[str]:
    return set(re.findall(r"[a-zа-яё0-9]{3,}", (query or "").lower()))


def _score_text(text: str, tokens: set[str]) -> int:
    if not tokens:
        return 0
    low = (text or "").lower()
    return sum(2 if t in low else 0 for t in tokens)


async def search_thread_history(
    db: AsyncSession,
    thread_id: UUID,
    query: str,
    *,
    limit: int = 12,
) -> list[dict[str, str]]:
    result = await db.execute(
        select(Message)
        .where(Message.thread_id == thread_id)
        .order_by(Message.created_at.asc())
    )
    messages = list(result.scalars().all())
    tokens = _tokenize(query)
    scored: list[tuple[int, Message]] = []
    for msg in messages:
        score = _score_text(msg.content or "", tokens)
        if score > 0:
            scored.append((score, msg))
    scored.sort(key=lambda x: (-x[0], x[1].created_at), reverse=False)
    if not scored and query.strip():
        recent = messages[-SEARCH_LIMIT:]
        scored = [(1, m) for m in recent]

    out: list[dict[str, str]] = []
    for score, msg in scored[:limit]:
        out.append(
            {
                "role": msg.role.value,
                "content": (msg.content or "")[:SNIPPET_LEN],
                "created_at": msg.created_at.isoformat(),
                "score": str(score),
            }
        )
    return out


async def update_thread_memory_after_turn(
    db: AsyncSession,
    redis_client,
    user,
    agent: AgentInstance,
    *,
    thread_id: UUID,
    user_text: str,
    assistant_text: str,
    tool_summary: str = "",
) -> AgentSpec:
    """Обновляет rolling summary в agent_spec после хода."""
    from app.services.providers.factory import resolve_runtime_providers

    spec = load_agent_spec(agent)
    llm, _, answer_model, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    prompt = (
        f"Предыдущая память:\n{spec.thread_memory[:2500] or '(пусто)'}\n\n"
        f"Пользователь: {user_text[:800]}\n"
        f"Ассистент: {assistant_text[:800]}\n"
    )
    if tool_summary:
        prompt += f"Инструменты: {tool_summary[:600]}\n"
    prompt += (
        "\nОбнови краткую память диалога (до 1200 символов): факты, решения, категории, "
        "chat_id, что договорились. Только текст памяти, без markdown."
    )
    try:
        if hasattr(llm, "complete_text"):
            new_memory = (
                await llm.complete_text(
                    [
                        {
                            "role": "system",
                            "text": "Сжимай контекст треда настройки агента Glosix. Сохраняй важные факты.",
                        },
                        {"role": "user", "text": prompt},
                    ],
                    model="pro" if answer_model == "pro" else "lite",
                    max_tokens=500,
                    temperature=0.2,
                )
            ).strip()
            if new_memory:
                spec.thread_memory = new_memory[:4000]
    except Exception as exc:
        logger.warning("thread_memory update failed: %s", exc)
        if user_text:
            append_fact(spec, f"Последний запрос: {user_text[:200]}")

    save_agent_spec(agent, spec)
    return spec


async def search_thread_history_tool(
    db: AsyncSession,
    thread_id: UUID,
    query: str,
) -> dict:
    items = await search_thread_history(db, thread_id, query)
    return {"ok": True, "tool": "search_thread_history", "result": {"items": items, "count": len(items)}}
