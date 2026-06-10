"""Компактные LLM-сводки для агентов (отдельно от search_flow)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_GROUP_SUMMARY_PROMPT = """Сожми сообщения группового чата в краткую сводку на русском (5–10 пунктов).
Выдели решения и вопросы. Без вводных фраз."""


async def summarize_group_buffer(
    db,
    redis_client,
    user,
    buffer: list[dict[str, Any]],
    *,
    header: str = "",
) -> str:
    if not buffer:
        return "Новых сообщений в группе с прошлой сводки нет."
    lines: list[str] = []
    for item in buffer[-15:]:
        author = str(item.get("author") or "?")[:40]
        text = str(item.get("text") or "")[:180]
        if text.strip():
            lines.append(f"{author}: {text}")
    if not lines:
        return "Новых сообщений в группе с прошлой сводки нет."

    compact_input = "\n".join(lines)
    if len(compact_input) < 120:
        bullets = "\n".join(f"• {line}" for line in lines)
        body = bullets
    else:
        from app.services.providers.factory import resolve_runtime_providers

        llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
        try:
            if hasattr(llm, "complete_text"):
                body = await llm.complete_text(  # type: ignore[attr-defined]
                    [
                        {"role": "system", "text": _GROUP_SUMMARY_PROMPT},
                        {"role": "user", "text": compact_input[:3500]},
                    ],
                    model="pro",
                    max_tokens=450,
                    temperature=0.2,
                )
            else:
                body = "\n".join(f"• {line}" for line in lines)
        except Exception as exc:
            logger.warning("Group summary LLM failed: %s", exc)
            body = "\n".join(f"• {line}" for line in lines)

    body = (body or "").strip()
    if header.strip():
        return f"{header.strip()}\n\n{body}"
    return body


_NEWS_SUMMARY_PROMPT = """Составь краткую новостную сводку на русском по результатам поиска.
3–6 пунктов, только факты из источников, без выдумок. Укажи тему в первой строке."""

_NEWS_POST_PROMPT = """Составь новостной пост на русском по результатам поиска для публикации в мессенджере.
Связный текст из 2–4 абзацев, только факты из источников, без выдумок.
Длина: от {min_chars} до {max_chars} символов. Заголовок темы в первой строке."""


async def summarize_search_sources(
    db,
    redis_client,
    user,
    topic: str,
    sources: list[Any],
    *,
    header: str = "",
    min_chars: int | None = None,
    max_chars: int | None = None,
) -> str:
    if not sources:
        return f"По теме «{topic}» свежих результатов не найдено."

    chunks: list[str] = []
    for src in sources[:5]:
        title = getattr(src, "title", None) or ""
        snippet = getattr(src, "snippet", None) or ""
        domain = getattr(src, "domain", None) or ""
        chunks.append(f"- {title} ({domain}): {str(snippet)[:300]}")
    context = "\n".join(chunks)

    from app.services.providers.factory import resolve_runtime_providers

    llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    if min_chars and max_chars and max_chars >= min_chars:
        system_prompt = _NEWS_POST_PROMPT.format(min_chars=min_chars, max_chars=max_chars)
        max_tokens = min(1200, max(600, max_chars // 2))
    else:
        system_prompt = _NEWS_SUMMARY_PROMPT
        max_tokens = 500
    try:
        if hasattr(llm, "complete_text"):
            body = await llm.complete_text(  # type: ignore[attr-defined]
                [
                    {"role": "system", "text": system_prompt},
                    {
                        "role": "user",
                        "text": f"Тема: {topic[:200]}\n\nИсточники:\n{context[:4000]}",
                    },
                ],
                model="pro",
                max_tokens=max_tokens,
                temperature=0.2,
            )
        else:
            body = context
    except Exception as exc:
        logger.warning("News summary LLM failed: %s", exc)
        body = context

    body = (body or "").strip()
    if header.strip():
        return f"{header.strip()}\n\n{body}"
    return body
