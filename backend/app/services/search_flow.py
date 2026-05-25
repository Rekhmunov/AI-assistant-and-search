import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import RateLimiter
from app.models.message import Message, MessageRole
from app.models.thread import Thread
from app.models.uploaded_file import UploadedFile
from app.models.user import Plan, User
from app.schemas.thread import SourceOut
from app.services.llm_provider import SearchSource
from app.services.yandex_gpt import YandexGPTProvider
from app.services.yandex_search import YandexSearchService


def sources_to_json(sources: list[SearchSource]) -> list[dict]:
    return [
        {
            "index": s.index,
            "url": s.url,
            "title": s.title,
            "snippet": s.snippet,
            "domain": s.domain,
        }
        for s in sources
    ]


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class SearchFlowService:
    def __init__(self):
        self.search = YandexSearchService()
        self.llm = YandexGPTProvider()

    async def _resolve_attachments(
        self,
        db: AsyncSession,
        user: User,
        query: str,
        attachment_ids: list[uuid.UUID] | None,
    ) -> tuple[str, str]:
        """Returns (llm/search query text, user-visible message content)."""
        if not attachment_ids:
            return query, query

        result = await db.execute(
            select(UploadedFile).where(
                UploadedFile.id.in_(attachment_ids),
                UploadedFile.user_id == user.id,
            )
        )
        files = list(result.scalars().all())
        if len(files) != len(attachment_ids):
            raise ValueError("attachment_not_found")

        names = [f.filename for f in files]
        parts = [query]
        for f in files:
            parts.append(f"\n\n--- Документ: {f.filename} ---\n{f.extracted_text}")
        llm_query = "\n".join(parts)
        display = f"{query}\n\n[Файлы: {', '.join(names)}]" if names else query
        return llm_query, display

    def _is_guest(self, user: User) -> bool:
        return bool(user.guest_key) and not user.email

    async def stream_search(
        self,
        db: AsyncSession,
        user: User,
        limiter: RateLimiter,
        query: str,
        thread_id: uuid.UUID | None,
        attachment_ids: list[uuid.UUID] | None = None,
    ) -> AsyncIterator[str]:
        if attachment_ids and self._is_guest(user):
            yield sse_event(
                "error",
                {"code": "auth_required", "message": "Войдите, чтобы прикреплять файлы"},
            )
            return

        allowed, used, limit = await limiter.check_search_limit(str(user.id), user.plan, user)
        if not allowed:
            yield sse_event("error", {"code": "rate_limit", "message": f"Лимит поисков: {limit}/день"})
            return

        if not await limiter.check_global_yandex_limit():
            await limiter.release_search(str(user.id))
            yield sse_event("error", {"code": "global_limit", "message": "Сервис временно перегружен"})
            return

        try:
            llm_query, display_content = await self._resolve_attachments(db, user, query, attachment_ids)
        except ValueError:
            yield sse_event("error", {"code": "attachment", "message": "Файл не найден или истёк"})
            return

        thread: Thread | None = None
        if thread_id:
            result = await db.execute(
                select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
            )
            thread = result.scalar_one_or_none()
            if not thread:
                yield sse_event("error", {"code": "not_found", "message": "Тред не найден"})
                return
        else:
            thread = Thread(user_id=user.id, title=display_content[:200])
            db.add(thread)
            await db.flush()

        user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=display_content)
        db.add(user_msg)
        await db.flush()

        yield sse_event("thread", {"thread_id": str(thread.id)})

        history: list[tuple[str, str]] = []
        if thread_id:
            msgs = await db.execute(
                select(Message)
                .where(Message.thread_id == thread.id, Message.id != user_msg.id)
                .order_by(Message.created_at)
            )
            for m in msgs.scalars().all():
                history.append((m.role.value, m.content))

        sources = await self.search.search(llm_query[:400])
        sources_json = sources_to_json(sources)
        yield sse_event("sources", {"sources": sources_json})

        full_answer = ""
        async for chunk in self.llm.stream_answer(llm_query, sources, history):
            full_answer += chunk
            yield sse_event("token", {"text": chunk})

        follow_ups = await self.llm.generate_follow_ups(llm_query, full_answer)

        assistant_msg = Message(
            thread_id=thread.id,
            role=MessageRole.ASSISTANT,
            content=full_answer.strip(),
            sources=sources_json,
            follow_up_questions=follow_ups,
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        if not thread_id:
            thread.title = display_content[:200]
        await db.commit()

        yield sse_event("follow_ups", {"questions": follow_ups})
        yield sse_event("done", {"message_id": str(assistant_msg.id), "searches_today": used, "searches_limit": limit})
