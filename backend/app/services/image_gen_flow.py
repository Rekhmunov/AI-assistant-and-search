"""SSE-поток генерации изображения по текстовому запросу."""

from __future__ import annotations

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
from app.services.image_gen_service import (
    persist_generated_image,
    resolve_image_gen_provider_id,
    stream_image_generation,
)
from app.services.message_images_column import messages_have_images_column
from app.services.image_bytes import is_valid_image_bytes
from app.services.service_incidents import record_service_incident
from app.services.sse import sse_event
from app.services.search_query import normalize_user_query

logger = logging.getLogger(__name__)

STATUS_MESSAGES = (
    "Запускаем генерацию…",
    "Делаем шедевр…",
    "Смешиваем краски…",
    "Почти готово…",
)


async def stream_image_generation_turn(
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

    if user.plan != Plan.PRO:
        yield sse_event(
            "error",
            {
                "code": "free_image_gen_pro",
                "message": (
                    "Генерация изображений доступна только в тарифе Pro. "
                    "Оформите подписку в профиле."
                ),
            },
        )
        return

    provider_id = await resolve_image_gen_provider_id(db, redis_client)
    if provider_id == "gigachat" and not settings.gigachat_configured:
        yield sse_event(
            "error",
            {
                "code": "image_gen_unavailable",
                "message": "GigaChat не настроен на сервере (GIGACHAT_CREDENTIALS).",
            },
        )
        return

    allowed, used, limit = await limiter.check_image_gen_limit(user_id_str, user.plan)
    if not allowed:
        yield sse_event(
            "error",
            {
                "code": "image_gen_rate_limit",
                "message": f"Лимит генераций изображений: {limit} в день. Попробуйте завтра.",
            },
        )
        return

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
            await limiter.release_image_gen(user_id_str)
            yield sse_event("error", {"code": "not_found", "message": "Тред не найден"})
            return
    else:
        thread = Thread(user_id=user.id, title=display_content[:200])
        db.add(thread)
        await db.flush()

    user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=display_content)
    db.add(user_msg)
    await db.flush()
    await db.commit()

    yield sse_event("thread", {"thread_id": str(thread.id)})
    yield sse_event(
        "route",
        {
            "needs_search": False,
            "answer_model": "pro",
            "reason": "image_generation",
            "intent": "image_generate",
            "policy_version": "v1",
        },
    )
    yield sse_event("image_gen_start", {"status": STATUS_MESSAGES[0]})

    image_bytes: bytes | None = None
    assistant_text = ""

    try:
        async for event_type, payload in stream_image_generation(display_content, provider_id):
            if event_type == "status" and payload:
                yield sse_event("image_gen_status", {"status": payload})
            elif event_type == "image_bytes" and isinstance(payload, bytes):
                image_bytes = payload
            elif event_type == "error":
                await record_service_incident(
                    redis_client,
                    service="image_gen",
                    kind="generation_failed",
                    message=str(payload),
                )
                await limiter.release_image_gen(user_id_str)
                yield sse_event(
                    "error",
                    {"code": "image_gen_failed", "message": payload},
                )
                return
            elif event_type == "done":
                lines = payload.split("\n", 1)
                assistant_text = lines[1].strip() if len(lines) > 1 else ""
    except Exception as exc:
        logger.exception("image generation failed")
        await record_service_incident(
            redis_client,
            service="image_gen",
            kind="exception",
            message=str(exc),
        )
        await limiter.release_image_gen(user_id_str)
        yield sse_event(
            "error",
            {
                "code": "image_gen_failed",
                "message": "Не удалось сгенерировать изображение. Попробуйте ещё раз.",
            },
        )
        return

    if not image_bytes or not is_valid_image_bytes(image_bytes):
        await record_service_incident(
            redis_client,
            service="image_gen",
            kind="invalid_image",
            message="Пустое или повреждённое изображение от GigaChat",
        )
        await limiter.release_image_gen(user_id_str)
        yield sse_event(
            "error",
            {
                "code": "image_gen_failed",
                "message": "Пустое или повреждённое изображение от сервиса генерации.",
            },
        )
        return

    _file_id, images_json = await persist_generated_image(
        db,
        user,
        image_bytes,
        title=display_content[:120],
    )

    if not assistant_text:
        assistant_text = "Готово — изображение сгенерировано."

    chunk_size = 24
    for i in range(0, len(assistant_text), chunk_size):
        yield sse_event("token", {"text": assistant_text[i : i + chunk_size]})

    yield sse_event("images", {"images": images_json})

    images_payload = images_json if await messages_have_images_column(db) else None
    assistant_msg = Message(
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=assistant_text,
        sources=None,
        images=images_payload,
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
        "done",
        {
            "message_id": str(assistant_msg.id),
            "searches_today": used,
            "searches_limit": limit,
            "needs_search": False,
            "answer_model": "pro",
            "image_gens_today": used,
            "image_gens_limit": limit,
        },
    )
