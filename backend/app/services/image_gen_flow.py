"""SSE-поток генерации изображения по текстовому запросу."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.message import Message, MessageRole
from app.models.thread import Thread, ThreadType
from app.models.user import Plan, User
from app.services.image_gen_service import (
    persist_generated_image,
    resolve_image_gen_provider_id,
    stream_image_generation,
)
from app.services.upload_lifecycle import resolve_generated_image_ttl_hours
from app.services.message_images_column import messages_have_images_column
from app.services.image_bytes import is_valid_image_bytes
from app.services.service_incidents import record_service_incident
from app.services.search_pending import clear_search_pending, set_search_pending, update_search_pending
from app.services.sse import sse_event
from app.services.search_query import normalize_user_query

logger = logging.getLogger(__name__)

STATUS_MESSAGES = (
    "Запускаем генерацию…",
    "Делаем шедевр…",
    "Смешиваем краски…",
    "Почти готово…",
)

# Интервал между автоматическими статусами (сек)
_STATUS_INTERVAL_SEC = 4.0


async def stream_image_generation_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
    *,
    high_quality: bool = False,
) -> AsyncIterator[str]:
    settings = get_settings()
    user_id_str = str(user.id)
    display_content = normalize_user_query(query).strip()
    image_size = "2K" if high_quality else "1K"

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
    if provider_id == "nanab2" and not settings.google_configured:
        yield sse_event(
            "error",
            {
                "code": "image_gen_unavailable",
                "message": "Nano Banana не настроен на сервере (GOOGLE_API_KEY).",
            },
        )
        return

    img_cost = 8 if high_quality else 3
    allowed, used, limit = await limiter.check_search_limit(
        user_id_str, user.plan, user=user, cost=img_cost
    )
    if not allowed:
        yield sse_event(
            "error",
            {
                "code": "image_gen_rate_limit",
                "message": f"Недостаточно кредитов: генерация {'2K' if high_quality else '1K'} стоит {img_cost} кредита. Осталось {limit - used}.",
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
            await limiter.release_search(user_id_str, user, cost=img_cost)
            yield sse_event("error", {"code": "not_found", "message": "Тред не найден"})
            return
        if thread.thread_type != ThreadType.SEARCH:
            await limiter.release_search(user_id_str, user, cost=img_cost)
            yield sse_event(
                "error",
                {
                    "code": "wrong_thread_type",
                    "message": "Этот диалог — настройка агента, не поиск.",
                },
            )
            return
    else:
        thread = Thread(
            user_id=user.id,
            title=display_content[:200],
            thread_type=ThreadType.SEARCH,
        )
        db.add(thread)
        await db.flush()

    user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=display_content)
    db.add(user_msg)
    await db.flush()
    await db.commit()

    await set_search_pending(
        redis_client,
        thread.id,
        user_message_id=user_msg.id,
        phase="image_generating",
        needs_search=False,
        intent="image_generate",
        custom_status=STATUS_MESSAGES[0],
    )

    logger.warning("IMGGEN_FLOW: yielding thread=%s user=%s", thread.id, user.id)
    yield sse_event("thread", {"thread_id": str(thread.id)})
    logger.warning("IMGGEN_FLOW: yielding route intent=image_generate thread=%s", thread.id)
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
    logger.warning("IMGGEN_FLOW: yielding image_gen_start status=%r thread=%s", STATUS_MESSAGES[0], thread.id)
    yield sse_event("image_gen_start", {"status": STATUS_MESSAGES[0]})

    # Запускаем реальную генерацию в фоновой задаче, чтобы параллельно
    # отправлять клиенту плановые статус-сообщения каждые ~4 секунды.
    gen_events: list[tuple[str, Any]] = []
    gen_exception: list[BaseException] = []
    gen_done = asyncio.Event()

    async def _run_generation() -> None:
        try:
            async for event_type, payload in stream_image_generation(
                display_content, provider_id, image_size=image_size
            ):
                gen_events.append((event_type, payload))
        except Exception as exc:  # noqa: BLE001
            gen_exception.append(exc)
        finally:
            gen_done.set()

    gen_task = asyncio.create_task(_run_generation())

    # Отправляем STATUS_MESSAGES[1..] каждые _STATUS_INTERVAL_SEC пока идёт генерация
    status_idx = 1
    while not gen_done.is_set():
        try:
            await asyncio.wait_for(asyncio.shield(gen_done.wait()), timeout=_STATUS_INTERVAL_SEC)
        except asyncio.TimeoutError:
            if status_idx < len(STATUS_MESSAGES):
                msg = STATUS_MESSAGES[status_idx]
                status_idx += 1
                await update_search_pending(redis_client, thread.id, custom_status=msg)
                logger.warning("IMGGEN_FLOW: yielding image_gen_status status=%r thread=%s", msg, thread.id)
                yield sse_event("image_gen_status", {"status": msg})

    await gen_task  # гарантируем завершение

    image_bytes: bytes | None = None
    assistant_text = ""

    # Разбираем накопленные события генерации
    try:
        if gen_exception:
            raise gen_exception[0]

        for event_type, payload in gen_events:
            if event_type == "image_bytes" and isinstance(payload, bytes):
                image_bytes = payload
            elif event_type == "error":
                await record_service_incident(
                    redis_client,
                    service="image_gen",
                    kind="generation_failed",
                    message=str(payload),
                )
                await limiter.release_search(user_id_str, user, cost=img_cost)
                yield sse_event(
                    "error",
                    {"code": "image_gen_failed", "message": payload},
                )
                return
            elif event_type == "done":
                lines = str(payload).split("\n", 1)
                assistant_text = lines[1].strip() if len(lines) > 1 else ""

    except Exception as exc:
        logger.exception("image generation failed")
        await record_service_incident(
            redis_client,
            service="image_gen",
            kind="exception",
            message=str(exc),
        )
        await limiter.release_search(user_id_str, user, cost=img_cost)
        await clear_search_pending(redis_client, thread.id)
        yield sse_event(
            "error",
            {
                "code": "image_gen_failed",
                "message": "Не удалось сгенерировать изображение. Попробуйте ещё раз.",
            },
        )
        return

    # --- Ниже: успешный путь; except выше уже вернулся при ошибке ---

    try:
        if not image_bytes or not is_valid_image_bytes(image_bytes):
            await record_service_incident(
                redis_client,
                service="image_gen",
                kind="invalid_image",
                message=f"Пустое или повреждённое изображение от {provider_id}",
            )
            await limiter.release_search(user_id_str, user, cost=img_cost)
            await clear_search_pending(redis_client, thread.id)
            yield sse_event(
                "error",
                {
                    "code": "image_gen_failed",
                    "message": "Пустое или повреждённое изображение от сервиса генерации.",
                },
            )
            return

        image_ttl_hours = await resolve_generated_image_ttl_hours(db, redis_client)
        _file_id, images_json = await persist_generated_image(
            db,
            user,
            image_bytes,
            title=display_content[:120],
            ttl_hours=image_ttl_hours,
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

        # Store image context for future edits (img2img)
        try:
            from app.services.image_edit_flow import set_thread_image_context
            await set_thread_image_context(redis_client, thread.id, str(_file_id))
        except Exception as _ctx_exc:
            logger.warning("IMGGEN_FLOW: failed storing image context: %s", _ctx_exc)

        logger.warning("IMGGEN_FLOW: yielding done thread=%s msg=%s", thread.id, assistant_msg.id)
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
    finally:
        await clear_search_pending(redis_client, thread.id)
