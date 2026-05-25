import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import RateLimiter
from app.models.message import Message, MessageRole
from app.models.thread import Thread
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.llm_provider import SearchSource
from app.services.query_router import QueryRouter
from app.services.search_debug import build_debug_trace, build_gpt_messages_preview
from app.services.search_query import enhance_search_query, is_howto_query, normalize_user_query
from app.services.source_ranking import rank_sources
from app.services.thread_context import build_thread_context, format_sources_for_prompt
from app.services.yandex_errors import YandexServiceError
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


logger = logging.getLogger(__name__)

_debug_trace_column_ok: bool | None = None


async def _messages_have_debug_trace(db: AsyncSession) -> bool:
    global _debug_trace_column_ok
    if _debug_trace_column_ok is not None:
        return _debug_trace_column_ok
    try:
        await db.execute(text("SELECT debug_trace FROM messages LIMIT 0"))
        _debug_trace_column_ok = True
    except ProgrammingError:
        _debug_trace_column_ok = False
        logger.warning("Column messages.debug_trace missing — run alembic upgrade head")
    return _debug_trace_column_ok


class SearchFlowService:
    def __init__(self):
        self.search = YandexSearchService()
        self.llm = YandexGPTProvider()
        self.router = QueryRouter()

    async def _resolve_attachments(
        self,
        db: AsyncSession,
        user: User,
        query: str,
        attachment_ids: list[uuid.UUID] | None,
    ) -> tuple[str, str]:
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
            llm_query, display_content = await self._resolve_attachments(
                db, user, normalize_user_query(query), attachment_ids
            )
        except ValueError:
            yield sse_event("error", {"code": "attachment", "message": "Файл не найден или истёк"})
            return

        has_attachments = bool(attachment_ids)

        thread: Thread | None = None
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
        else:
            thread = Thread(user_id=user.id, title=display_content[:200])
            db.add(thread)
            await db.flush()

        prior_messages: list[Message] = []
        if thread_id:
            msgs_result = await db.execute(
                select(Message)
                .where(Message.thread_id == thread.id)
                .order_by(Message.created_at)
            )
            prior_messages = list(msgs_result.scalars().all())

        thread_ctx = build_thread_context(prior_messages)
        route = await self.router.route(llm_query, thread_ctx, has_attachments, user.plan)

        user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=display_content)
        db.add(user_msg)
        await db.flush()

        yield sse_event("thread", {"thread_id": str(thread.id)})
        yield sse_event(
            "route",
            {
                "needs_search": route.needs_search,
                "answer_model": route.answer_model,
                "reason": route.reason,
            },
        )

        history = thread_ctx.history
        prior_sources_block = format_sources_for_prompt(thread_ctx.last_assistant_sources)

        sources: list[SearchSource] = []
        sources_json: list[dict] = []
        search_q_sent: str | None = None

        try:
            if route.needs_search:
                search_q_sent = enhance_search_query(
                    route.search_query,
                    for_howto=is_howto_query(llm_query) or route.reason.startswith("rules:howto"),
                )
                raw_sources = await self.search.search(search_q_sent)
                sources = rank_sources(
                    raw_sources,
                    howto=is_howto_query(llm_query) or route.answer_model == "pro",
                )
                sources_json = sources_to_json(sources)
                yield sse_event("sources", {"sources": sources_json})

            gpt_preview = build_gpt_messages_preview(
                self.llm,
                llm_query=llm_query,
                sources=sources,
                history=history,
                prior_sources_block=prior_sources_block,
                needs_search=route.needs_search,
                model=route.answer_model,
            )

            full_answer = ""
            if route.needs_search:
                async for chunk in self.llm.stream_answer(
                    llm_query,
                    sources,
                    history,
                    model=route.answer_model,
                    prior_sources_block=prior_sources_block,
                ):
                    full_answer += chunk
                    yield sse_event("token", {"text": chunk})
            else:
                async for chunk in self.llm.stream_answer_direct(
                    llm_query,
                    history,
                    model=route.answer_model,
                    prior_sources_block=prior_sources_block,
                ):
                    full_answer += chunk
                    yield sse_event("token", {"text": chunk})
        except YandexServiceError as e:
            await db.rollback()
            await limiter.release_search(str(user.id))
            yield sse_event(
                "error",
                {"code": "yandex_error", "message": str(e)},
            )
            return

        follow_ups = await self.llm.generate_follow_ups(llm_query, full_answer)

        debug_trace = build_debug_trace(
            display_content=display_content,
            llm_query=llm_query,
            route=route,
            search_query_sent=search_q_sent,
            sources=sources,
            sources_json=sources_json,
            needs_search=route.needs_search,
            answer_model=route.answer_model,
            gpt_messages_preview=gpt_preview,
        )

        trace_payload = debug_trace if await _messages_have_debug_trace(db) else None
        assistant_msg = Message(
            thread_id=thread.id,
            role=MessageRole.ASSISTANT,
            content=full_answer.strip(),
            sources=sources_json if sources_json else None,
            follow_up_questions=follow_ups,
            debug_trace=trace_payload,
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        if not thread_id:
            thread.title = display_content[:200]
        await db.commit()

        yield sse_event("follow_ups", {"questions": follow_ups})
        yield sse_event(
            "done",
            {
                "message_id": str(assistant_msg.id),
                "searches_today": used,
                "searches_limit": limit,
                "needs_search": route.needs_search,
                "answer_model": route.answer_model,
            },
        )
