"""SSE-поток генерации Word-документа."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.message import Message, MessageRole
from app.models.thread import Thread
from app.models.user import Plan, User
from app.services.app_settings import get_setting
from app.services.doc_gen_context import (
    build_doc_gen_user_message,
    prior_assistant_source_text,
    refers_to_prior_answer,
)
from app.services.doc_gen_llm import generate_document_structure
from app.services.doc_gen_plain import structure_from_plain_text
from app.services.doc_gen_routing import resolve_output_format
from app.services.doc_gen_schema import DocumentStructureError
from app.services.doc_gen_storage import persist_generated_docx
from app.services.docx_builder import build_docx_bytes
from app.services.file_share_token import create_file_share_token
from app.services.providers.factory import resolve_runtime_providers
from app.services.search_query import normalize_user_query
from app.services.search_pending import clear_search_pending, set_search_pending, update_search_pending
from app.services.sse import sse_event

logger = logging.getLogger(__name__)

STATUS_MESSAGES = (
    "Анализируем запрос…",
    "Готовим структуру документа…",
    "Прописываем разделы…",
    "Формируем формулировки…",
    "Согласуем текст…",
    "Проверяем оформление…",
    "Собираем файл Word…",
)

DOC_GEN_STATUS_PAUSE_SEC = 2.5


def _assistant_message_text(ttl_hours: int) -> str:
    return (
        "Вот готовый файл, можете его скачать. "
        f"Напоминаем, файл хранится {ttl_hours} часов."
    )


def _is_guest(user: User) -> bool:
    return bool(user.guest_key) and not user.email


async def stream_document_generation_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
) -> AsyncIterator[str]:
    settings = get_settings()
    user_id_str = str(user.id)
    display_content = normalize_user_query(query).strip()
    output_format = resolve_output_format(display_content)

    if output_format == "pdf":
        yield sse_event(
            "error",
            {
                "code": "doc_gen_format_unavailable",
                "message": "Экспорт в PDF скоро появится. Пока доступен формат Word (.docx).",
            },
        )
        return

    allowed, used, limit = await limiter.check_doc_gen_allowed(user_id_str, user)
    if not allowed:
        if _is_guest(user):
            yield sse_event(
                "error",
                {
                    "code": "doc_gen_guest_limit",
                    "message": (
                        "Гостевой лимит генерации документов исчерпан. "
                        "Зарегистрируйтесь, чтобы продолжить."
                    ),
                },
            )
        elif user.plan != Plan.PRO:
            yield sse_event(
                "error",
                {
                    "code": "doc_gen_rate_limit",
                    "message": (
                        "На сегодня лимиты по генерации документов закончены. "
                        "Продолжить генерацию можно будет завтра."
                    ),
                },
            )
        else:
            yield sse_event(
                "error",
                {
                    "code": "doc_gen_rate_limit",
                    "message": (
                        "На сегодня лимиты по генерации документов закончены. "
                        "Продолжить генерацию можно будет завтра."
                    ),
                },
            )
        return

    ttl_hours = int(
        await get_setting("generated_doc_ttl_hours", db, redis_client, settings)
    )
    ttl_hours = max(1, min(ttl_hours, 24 * 30))

    llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    answer_model = "pro" if user.plan == Plan.PRO else "lite"

    prior_messages: list[Message] = []

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
        msg_result = await db.execute(
            select(Message)
            .where(Message.thread_id == thread.id)
            .order_by(Message.created_at.asc())
        )
        prior_messages = list(msg_result.scalars().all())
    else:
        thread = Thread(user_id=user.id, title=display_content[:200])
        db.add(thread)
        await db.flush()

    doc_gen_prompt = build_doc_gen_user_message(display_content, prior_messages)

    user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=display_content)
    db.add(user_msg)
    await db.flush()
    await db.commit()

    await set_search_pending(
        redis_client,
        thread.id,
        user_message_id=user_msg.id,
        phase="document_generating",
        needs_search=False,
        intent="generate_document",
        custom_status=STATUS_MESSAGES[0],
    )

    yield sse_event("thread", {"thread_id": str(thread.id)})
    yield sse_event(
        "route",
        {
            "needs_search": False,
            "answer_model": answer_model,
            "reason": "document_generation",
            "intent": "generate_document",
            "output_format": "docx",
            "policy_version": "v1",
        },
    )
    yield sse_event("doc_gen_start", {"status": STATUS_MESSAGES[0]})

    show_glosix = user.plan != Plan.PRO
    assistant_text = _assistant_message_text(ttl_hours)

    try:
        prior_source = prior_assistant_source_text(prior_messages)
        use_plain = bool(
            prior_source and refers_to_prior_answer(display_content)
        )

        async def _resolve_structure():
            if use_plain and prior_source:
                plain = structure_from_plain_text(prior_source)
                if plain is not None:
                    return plain
            return await generate_document_structure(
                llm,
                doc_gen_prompt,
                answer_model=answer_model,
            )

        structure_task = asyncio.create_task(_resolve_structure())
        tick = 0
        while not structure_task.done():
            msg = STATUS_MESSAGES[1 + (tick % max(len(STATUS_MESSAGES) - 2, 1))]
            tick += 1
            await update_search_pending(redis_client, thread.id, custom_status=msg)
            yield sse_event("doc_gen_status", {"status": msg})
            done, _ = await asyncio.wait({structure_task}, timeout=DOC_GEN_STATUS_PAUSE_SEC)
            if structure_task in done:
                break
        structure = structure_task.result()

        for post_msg in STATUS_MESSAGES[-2:]:
            await update_search_pending(redis_client, thread.id, custom_status=post_msg)
            yield sse_event("doc_gen_status", {"status": post_msg})
            await asyncio.sleep(DOC_GEN_STATUS_PAUSE_SEC)

        docx_bytes = build_docx_bytes(structure, show_glosix_footer=show_glosix)
        if len(docx_bytes) < 256:
            raise DocumentStructureError("empty_docx")
        file_id, filename, download_url = await persist_generated_docx(
            db,
            user,
            docx_bytes,
            title=structure.title,
            ttl_hours=ttl_hours,
        )
        share_token, _ = create_file_share_token(
            file_id,
            ttl_seconds=ttl_hours * 3600,
            settings=settings,
        )
        share_path = f"/api/files/{file_id}/shared?token={share_token}"
        attachments_payload = [
            {
                "id": str(file_id),
                "filename": filename,
                "kind": "document",
                "url": download_url,
                "share_url": share_path,
                "ttl_hours": ttl_hours,
            }
        ]
    except DocumentStructureError:
        logger.warning("doc gen structure failed for user %s", user_id_str)
        await clear_search_pending(redis_client, thread.id)
        yield sse_event(
            "error",
            {
                "code": "doc_gen_failed",
                "message": "Не удалось сформировать документ. Уточните запрос и попробуйте снова.",
            },
        )
        return
    except Exception:
        logger.exception("doc gen failed")
        await clear_search_pending(redis_client, thread.id)
        yield sse_event(
            "error",
            {
                "code": "doc_gen_failed",
                "message": "Не удалось сформировать документ. Попробуйте ещё раз.",
            },
        )
        return

    chunk_size = 32
    for i in range(0, len(assistant_text), chunk_size):
        yield sse_event("token", {"text": assistant_text[i : i + chunk_size]})

    assistant_msg = Message(
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=assistant_text,
        sources=None,
        images=None,
        attachments=attachments_payload,
        follow_up_questions=None,
        debug_trace=None,
    )
    db.add(assistant_msg)
    thread.message_count = (thread.message_count or 0) + 2
    thread.last_message_at = datetime.now(timezone.utc)
    if not thread_id:
        thread.title = display_content[:200]
    await db.commit()

    yield sse_event(
        "document_ready",
        {
            "file_id": str(file_id),
            "filename": filename,
            "download_url": download_url,
            "share_url": share_path,
            "ttl_hours": ttl_hours,
        },
    )

    await limiter.record_doc_gen_success(user_id_str, user)
    used_after, limit_after = await limiter.get_doc_gen_usage(user_id_str, user)

    yield sse_event(
        "done",
        {
            "message_id": str(assistant_msg.id),
            "needs_search": False,
            "answer_model": answer_model,
            "doc_gens_today": used_after,
            "doc_gens_limit": limit_after,
        },
    )
    await clear_search_pending(redis_client, thread.id)
