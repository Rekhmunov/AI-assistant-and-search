"""Экспорт уже написанного в чате текста: markdown-блок + скачивание docx по кнопке."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import RateLimiter
from app.models.message import Message, MessageRole
from app.models.thread import Thread, ThreadType
from app.models.user import User
from app.services.doc_gen_context import prior_assistant_source_text
from app.services.doc_gen_markdown import plain_answer_to_markdown
from app.services.search_query import normalize_user_query
from app.services.sse import sse_event


def _assistant_intro() -> str:
    return (
        "Ниже оформлен текст из предыдущего ответа. Его можно скопировать "
        "или скачать в Word или PDF — содержание не переписывается."
    )


async def stream_export_chat_document_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
) -> AsyncIterator[str]:
    display_content = normalize_user_query(query).strip()

    if thread_id:
        result = await db.execute(
            select(Thread).where(
                Thread.id == thread_id,
                Thread.user_id == user.id,
                Thread.deleted_at.is_(None),
            )
        )
        thread = result.scalar_one_or_none()
        if not thread:
            yield sse_event("error", {"code": "not_found", "message": "Тред не найден"})
            return
        if thread.thread_type != ThreadType.SEARCH:
            if thread.thread_type != ThreadType.AGENT:
                yield sse_event(
                    "error",
                    {
                        "code": "wrong_thread_type",
                        "message": "Этот диалог — настройка агента, не поиск.",
                    },
                )
                return
            from app.services.agent.doc_routing import agent_message_uses_search_flow

            if not agent_message_uses_search_flow(display_content, has_attachments=False):
                yield sse_event(
                    "error",
                    {
                        "code": "wrong_thread_type",
                        "message": (
                            "В этом диалоге настраивается агент MAX. "
                            "Для оформления документа напишите, например: «оформи текст выше в документ»."
                        ),
                    },
                )
                return
        msg_result = await db.execute(
            select(Message)
            .where(Message.thread_id == thread.id)
            .order_by(Message.created_at.asc())
        )
        prior_messages = list(msg_result.scalars().all())
    else:
        yield sse_event(
            "error",
            {
                "code": "no_thread",
                "message": "Откройте диалог с ответом, который нужно оформить в документ.",
            },
        )
        return

    source = prior_assistant_source_text(prior_messages)
    if not source:
        yield sse_event(
            "error",
            {
                "code": "no_prior_text",
                "message": "В переписке нет текста для оформления. Сначала получите ответ в чате.",
            },
        )
        return

    title, markdown = plain_answer_to_markdown(source)
    user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=display_content)
    db.add(user_msg)
    await db.flush()

    yield sse_event("thread", {"thread_id": str(thread.id)})
    yield sse_event(
        "route",
        {
            "needs_search": False,
            "answer_model": "lite",
            "reason": "export_chat_document",
            "intent": "export_chat_document",
            "policy_version": "v1",
        },
    )

    intro = _assistant_intro()
    for i in range(0, len(intro), 24):
        yield sse_event("token", {"text": intro[i : i + 24]})

    markdown_payload = {
        "title": title,
        "content": markdown,
        "collapsible": False,  # документы показываем полностью, не схлопываем
    }
    attachments_payload = [
        {
            "id": "markdown",
            "filename": f"{title[:80]}.md",
            "kind": "markdown_document",
            "title": title,
            "content": markdown,
        }
    ]

    assistant_msg = Message(
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=intro,
        sources=None,
        images=None,
        attachments=attachments_payload,
        follow_up_questions=None,
        debug_trace=None,
    )
    db.add(assistant_msg)
    thread.message_count = (thread.message_count or 0) + 2
    thread.last_message_at = datetime.now(timezone.utc)
    await db.commit()

    yield sse_event("markdown_document", markdown_payload)

    yield sse_event(
        "done",
        {
            "message_id": str(assistant_msg.id),
            "needs_search": False,
            "answer_model": "lite",
        },
    )
