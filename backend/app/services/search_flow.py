import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.message import Message, MessageRole
from app.models.thread import Thread
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.llm_provider import SearchSource
from app.services.answer_guard import is_template_evasion
from app.services.query_router import QueryRouter
from app.services.query_rewriter import QueryRewriter
from app.services.facts.pipeline import FactPipeline
from app.services.facts.verify import verify_answer_against_facts
from app.services.search_debug import build_debug_trace, build_gpt_messages_preview
from app.services.facts.slots import resolve_fact_slots
from app.services.search_query import enhance_search_query, normalize_user_query
from app.services.thread_context import build_thread_context, format_sources_for_prompt
from app.services.yandex_errors import YandexServiceError
from app.services.yandex_gpt import YandexGPTProvider
from app.services.query_url_memory import (
    QueryUrlMemoryTrace,
    lookup_bootstrap_sources,
    record_successful_urls,
)
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


_VALID_INTENTS: frozenset[str] = frozenset(
    {"factual_current", "howto", "document", "edit_prior", "compare_analyze", "chitchat"}
)


class SearchFlowService:
    def __init__(self):
        self.search = YandexSearchService()
        self.llm = YandexGPTProvider()
        self.router = QueryRouter()
        self.rewriter = QueryRewriter()
        self.fact_pipeline = FactPipeline(self.search, self.llm)

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
                "intent": route.intent,
                "policy_version": route.policy_version,
            },
        )

        history = thread_ctx.history
        prior_sources_block = format_sources_for_prompt(thread_ctx.last_assistant_sources)

        sources: list[SearchSource] = []
        sources_json: list[dict] = []
        search_q_sent: str | None = None
        rewrite_trace: dict | None = None
        search_attempts: list[dict] = []
        retrieval_trace: dict | None = None
        hint_clarify: str | None = None
        fact_pack = None
        query_url_trace: QueryUrlMemoryTrace | None = None

        try:
            if route.needs_search:
                rewrite, (bootstrap_sources, query_url_trace) = await asyncio.gather(
                    self.rewriter.rewrite(llm_query, thread_ctx),
                    lookup_bootstrap_sources(db, llm_query, llm_query),
                )
                fact_slots = resolve_fact_slots(rewrite.fact_slots)
                rewrite_trace = {
                    "search_queries": rewrite.search_queries,
                    "needs_clarification": rewrite.needs_clarification,
                    "clarification_question": rewrite.clarification_question,
                    "intent": rewrite.intent,
                    "fact_slots": fact_slots,
                    "reason": rewrite.reason,
                }
                if rewrite.intent in _VALID_INTENTS:
                    route.intent = rewrite.intent  # type: ignore[assignment]
                if rewrite.intent == "howto":
                    route.answer_model = "pro"

                if rewrite.needs_clarification and rewrite.clarification_question:
                    hint_clarify = rewrite.clarification_question

                queries = list(rewrite.search_queries or [route.search_query])
                howto = rewrite.intent == "howto"
                if howto or "course_program" in fact_slots:
                    route.answer_model = "pro"

                def _enhance(q: str) -> str:
                    return enhance_search_query(q, for_howto=howto)

                page_cache_trace: dict | None = None
                extra_boot, extra_trace = await lookup_bootstrap_sources(
                    db,
                    llm_query,
                    *(queries[:2]),
                )
                if extra_boot:
                    seen = {(s.url or "").lower() for s in bootstrap_sources}
                    for s in extra_boot:
                        u = (s.url or "").lower()
                        if u and u not in seen:
                            bootstrap_sources.append(s)
                            seen.add(u)
                if extra_trace.lookup_keys:
                    query_url_trace.lookup_keys = max(
                        query_url_trace.lookup_keys,
                        extra_trace.lookup_keys,
                    )
                    query_url_trace.bootstrap_count += extra_trace.bootstrap_count

                pipeline_result = await self.fact_pipeline.run(
                    llm_query,
                    queries,
                    enhance_fn=_enhance,
                    fact_slots=fact_slots,
                    howto=howto,
                    answer_model=route.answer_model,
                    bootstrap_sources=bootstrap_sources or None,
                )
                sources = pipeline_result.sources
                fact_pack = pipeline_result.fact_pack
                search_attempts = pipeline_result.search_attempts
                retrieval_trace = pipeline_result.retrieval_trace
                search_q_sent = pipeline_result.last_search_query
                page_cache_trace = pipeline_result.page_cache

                sources_json = sources_to_json(sources)
                if sources_json:
                    yield sse_event("sources", {"sources": sources_json})

            gpt_preview = build_gpt_messages_preview(
                self.llm,
                llm_query=llm_query,
                sources=sources,
                history=history,
                prior_sources_block=prior_sources_block,
                needs_search=route.needs_search,
                model=route.answer_model,
                hint_clarify=hint_clarify,
                fact_pack=fact_pack,
            )

            full_answer = ""
            if route.needs_search:
                weak_retrieval = bool(retrieval_trace and not retrieval_trace.get("ok"))

                full_answer = ""
                async for chunk in self.llm.stream_answer(
                    llm_query,
                    sources,
                    history,
                    model=route.answer_model,
                    prior_sources_block=prior_sources_block,
                    hint_clarify=hint_clarify,
                    strict_facts=weak_retrieval,
                    fact_pack=fact_pack,
                    intent_howto=howto,
                ):
                    full_answer += chunk
                    yield sse_event("token", {"text": chunk})

                if fact_pack and fact_pack.facts:
                    ok, unsupported = verify_answer_against_facts(
                        full_answer,
                        fact_pack,
                        fact_slots=fact_slots,
                    )
                    if not ok:
                        logger.info("Answer verify failed, unsupported numbers: %s", unsupported)
                        yield sse_event("reset_answer", {})
                        full_answer = ""
                        async for chunk in self.llm.stream_answer(
                            llm_query,
                            sources,
                            history,
                            model=route.answer_model,
                            prior_sources_block=prior_sources_block,
                            hint_clarify=hint_clarify,
                            strict_facts=True,
                            fact_pack=fact_pack,
                        ):
                            full_answer += chunk
                            yield sse_event("token", {"text": chunk})
                if is_template_evasion(full_answer):
                    logger.info("Answer template/refusal detected, regenerating")
                    yield sse_event("reset_answer", {})
                    full_answer = ""
                    async for chunk in self.llm.stream_answer(
                        llm_query,
                        sources,
                        history,
                        model=route.answer_model,
                        prior_sources_block=prior_sources_block,
                        hint_clarify=hint_clarify,
                        strict_facts=True,
                        fact_pack=fact_pack,
                        intent_howto=howto,
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

        settings = get_settings()
        follow_ups: list[str] = []
        follow_up_task: asyncio.Task[list[str]] | None = None
        if full_answer.strip():
            if settings.follow_ups_deferred:
                follow_up_task = asyncio.create_task(
                    self.llm.generate_follow_ups(llm_query, full_answer)
                )
            else:
                follow_ups = await self.llm.generate_follow_ups(llm_query, full_answer)

        if (
            route.needs_search
            and sources
            and query_url_trace is not None
            and full_answer.strip()
            and not is_template_evasion(full_answer)
        ):
            retrieval_ok = bool(retrieval_trace and retrieval_trace.get("ok"))
            has_facts = bool(fact_pack and fact_pack.facts)
            if retrieval_ok or has_facts:
                score = float((retrieval_trace or {}).get("score") or 0.35)
                query_url_trace.recorded_count = await record_successful_urls(
                    db,
                    llm_query,
                    sources,
                    retrieval_score=score,
                )

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
            rewrite=rewrite_trace,
            search_attempts=search_attempts or None,
            retrieval=retrieval_trace,
            fact_pack=fact_pack.to_dict() if fact_pack else None,
            page_cache=page_cache_trace,
            query_url_memory=query_url_trace.to_dict() if query_url_trace else None,
        )

        trace_payload = debug_trace if await _messages_have_debug_trace(db) else None
        assistant_msg = Message(
            thread_id=thread.id,
            role=MessageRole.ASSISTANT,
            content=full_answer.strip(),
            sources=sources_json if sources_json else None,
            follow_up_questions=follow_ups or None,
            debug_trace=trace_payload,
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        if not thread_id:
            thread.title = display_content[:200]
        await db.commit()

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

        if follow_up_task is not None:
            follow_ups = await follow_up_task
            assistant_msg.follow_up_questions = follow_ups
            await db.commit()
            yield sse_event("follow_ups", {"questions": follow_ups})
        elif follow_ups:
            yield sse_event("follow_ups", {"questions": follow_ups})
