"""SSE-поток редактирования / композиции изображений через Nano Banana 2.

image_edit:  тред содержит ранее сгенерированное изображение → img2img
image_compose: пользователь прикрепил 2+ изображений → объединить
"""
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
from app.models.thread import Thread, ThreadType
from app.models.user import Plan, User
from app.services.image_gen_service import persist_generated_image, resolve_image_gen_provider_id
from app.services.image_bytes import is_valid_image_bytes
from app.services.message_images_column import messages_have_images_column
from app.services.upload_storage import load_upload_bytes
from app.services.search_pending import clear_search_pending, set_search_pending, update_search_pending
from app.services.service_incidents import record_service_incident
from app.services.sse import sse_event
from app.services.upload_lifecycle import resolve_generated_image_ttl_hours
from app.services.image_gen_flow import STATUS_MESSAGES, _STATUS_INTERVAL_SEC

logger = logging.getLogger(__name__)

_THREAD_IMG_CTX_TTL = 72 * 3600  # 72h — match generated image TTL
_THREAD_IMG_CTX_KEY = "thread_last_img:{thread_id}"


async def get_thread_image_context(redis_client, thread_id) -> str | None:
    """Return file_id of the last generated image in this thread, or None."""
    key = _THREAD_IMG_CTX_KEY.format(thread_id=str(thread_id))
    val = await redis_client.get(key)
    return str(val) if val else None


async def set_thread_image_context(redis_client, thread_id, file_id: str) -> None:
    """Store the file_id of the latest generated image for this thread."""
    key = _THREAD_IMG_CTX_KEY.format(thread_id=str(thread_id))
    await redis_client.set(key, file_id, ex=_THREAD_IMG_CTX_TTL)


async def stream_image_edit_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
    *,
    attachment_ids: list[uuid.UUID] | None = None,
    compose_mode: bool = False,  # True = image_compose, False = image_edit
) -> AsyncIterator[str]:
    """
    SSE flow for img2img editing and image composition.

    image_edit: loads previous generated image from Redis context → modifies it.
    image_compose: loads 2+ attached images → composes them per instruction.
    """
    settings = get_settings()
    user_id_str = str(user.id)
    intent = "image_compose" if compose_mode else "image_edit"

    # ── Pro plan required ──
    if user.plan != Plan.PRO:
        yield sse_event("error", {
            "code": "free_image_gen_pro",
            "message": "Генерация и редактирование изображений доступны только в тарифе Pro. "
                       "Оформите подписку в профиле.",
        })
        return

    # ── Check provider ──
    provider_id = await resolve_image_gen_provider_id(db, redis_client)
    if provider_id != "nanab2":
        yield sse_event("error", {
            "code": "image_gen_unavailable",
            "message": "Редактирование изображений доступно только с провайдером Nano Banana 2. "
                       "В настройках администратора выберите Nano Banana 2.",
        })
        return

    if not settings.google_configured:
        yield sse_event("error", {
            "code": "image_gen_unavailable",
            "message": "Nano Banana не настроен на сервере (GOOGLE_API_KEY).",
        })
        return

    # ── Rate limit ──
    allowed, _used, _limit = await limiter.check_search_limit(user_id_str, user.plan, user=user, cost=3)
    if not allowed:
        yield sse_event("error", {
            "code": "image_gen_rate_limit",
            "message": f"Лимит генераций изображений: {_limit} в день. Попробуйте завтра.",
        })
        return

    # ── Find or create thread ──
    if thread_id:
        res = await db.execute(
            select(Thread).where(
                Thread.id == thread_id,
                Thread.user_id == user.id,
                Thread.deleted_at.is_(None),
            )
        )
        thread = res.scalar_one_or_none()
        if not thread:
            await limiter.release_search(user_id_str, user, cost=3)
            yield sse_event("error", {"code": "not_found", "message": "Тред не найден"})
            return
        if thread.thread_type != ThreadType.SEARCH:
            await limiter.release_search(user_id_str, user, cost=3)
            yield sse_event("error", {"code": "wrong_thread_type",
                                      "message": "Этот диалог — настройка агента, не поиск."})
            return
    else:
        thread = Thread(
            user_id=user.id,
            title=(query[:60] or ("Компоновка изображений" if compose_mode else "Редактирование изображения")),
            thread_type=ThreadType.SEARCH,
        )
        db.add(thread)
        await db.flush()

    # ── Save user message ──
    display_content = (query or "").strip() or (
        "Объедини изображения" if compose_mode else "Отредактируй изображение"
    )
    user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=display_content)
    db.add(user_msg)
    await db.flush()
    await db.commit()

    await set_search_pending(
        redis_client, thread.id,
        user_message_id=user_msg.id,
        phase="image_generating",
        needs_search=False,
        intent=intent,
        custom_status=STATUS_MESSAGES[0],
    )

    yield sse_event("thread", {"thread_id": str(thread.id)})
    yield sse_event("route", {
        "needs_search": False,
        "answer_model": "pro",
        "reason": intent,
        "intent": intent,
        "policy_version": "v1",
    })
    yield sse_event("image_gen_start", {"status": STATUS_MESSAGES[0]})

    # ── Load input images ──
    input_images: list[bytes] = []

    if compose_mode and attachment_ids:
        # Composition: load all attached images
        from app.models.uploaded_file import UploadedFile
        for fid in attachment_ids:
            res = await db.execute(
                select(UploadedFile).where(
                    UploadedFile.id == fid,
                    UploadedFile.user_id == user.id,
                )
            )
            uf = res.scalar_one_or_none()
            if uf and uf.storage_key:
                img = load_upload_bytes(uf.storage_key)
                if img:
                    input_images.append(img)
        if not input_images:
            await limiter.release_search(user_id_str, user, cost=3)
            await clear_search_pending(redis_client, thread.id)
            yield sse_event("error", {
                "code": "image_edit_failed",
                "message": "Не удалось загрузить прикреплённые изображения.",
            })
            return
    else:
        # Edit: prefer attached image, then fall back to last generated image in thread
        from app.models.uploaded_file import UploadedFile
        from uuid import UUID as _UUID

        # 1. Try attached images first (user uploaded their own photo to edit)
        if attachment_ids:
            for fid in attachment_ids:
                try:
                    res = await db.execute(
                        select(UploadedFile).where(
                            UploadedFile.id == fid,
                            UploadedFile.user_id == user.id,
                        )
                    )
                    uf = res.scalar_one_or_none()
                    if uf and uf.storage_key:
                        from app.services.image_bytes import is_valid_image_bytes
                        img = load_upload_bytes(uf.storage_key)
                        if img:
                            input_images.append(img)
                except Exception as exc:
                    logger.warning("image_edit: failed loading attachment %s: %s", fid, exc)

        # 2. Fall back to last generated image stored in Redis thread context
        if not input_images:
            prev_file_id = await get_thread_image_context(redis_client, thread.id)
            if not prev_file_id:
                await limiter.release_search(user_id_str, user, cost=3)
                await clear_search_pending(redis_client, thread.id)
                yield sse_event("error", {
                    "code": "image_edit_failed",
                    "message": "Прикрепите фото к сообщению или сначала сгенерируйте изображение командой «нарисуй …».",
                })
                return

            try:
                res = await db.execute(
                    select(UploadedFile).where(
                        UploadedFile.id == _UUID(prev_file_id),
                        UploadedFile.user_id == user.id,
                    )
                )
                uf = res.scalar_one_or_none()
                if uf and uf.storage_key:
                    img = load_upload_bytes(uf.storage_key)
                    if img:
                        input_images.append(img)
            except Exception as exc:
                logger.warning("image_edit: failed loading context image %s: %s", prev_file_id, exc)

        if not input_images:
            await limiter.release_search(user_id_str, user, cost=3)
            await clear_search_pending(redis_client, thread.id)
            yield sse_event("error", {
                "code": "image_edit_failed",
                "message": "Не удалось загрузить исходное изображение. Попробуйте ещё раз.",
            })
            return

    # ── Run generation in background, send status updates ──
    from app.services.nano_banana import generate_nano_banana_image, NanaBananaResult

    gen_result: list[NanaBananaResult] = []
    gen_exception: list[BaseException] = []
    gen_done = asyncio.Event()

    async def _run_edit() -> None:
        try:
            result = await generate_nano_banana_image(
                query,
                api_key=settings.google_api_key,
                input_images=input_images,
            )
            gen_result.append(result)
        except Exception as exc:  # noqa: BLE001
            gen_exception.append(exc)
        finally:
            gen_done.set()

    gen_task = asyncio.create_task(_run_edit())

    status_idx = 1
    while not gen_done.is_set():
        try:
            await asyncio.wait_for(asyncio.shield(gen_done.wait()), timeout=_STATUS_INTERVAL_SEC)
        except asyncio.TimeoutError:
            if status_idx < len(STATUS_MESSAGES):
                msg = STATUS_MESSAGES[status_idx]
                status_idx += 1
                await update_search_pending(redis_client, thread.id, custom_status=msg)
                yield sse_event("image_gen_status", {"status": msg})

    await gen_task

    if gen_exception:
        exc = gen_exception[0]
        await record_service_incident(redis_client, service="image_gen",
                                      kind="edit_failed", message=str(exc))
        await limiter.release_search(user_id_str, user, cost=3)
        await clear_search_pending(redis_client, thread.id)
        yield sse_event("error", {
            "code": "image_gen_failed",
            "message": f"Не удалось {'объединить' if compose_mode else 'отредактировать'} изображение: {exc}",
        })
        return

    if not gen_result or not gen_result[0].image_bytes:
        await limiter.release_search(user_id_str, user, cost=3)
        await clear_search_pending(redis_client, thread.id)
        yield sse_event("error", {"code": "image_gen_failed",
                                  "message": "Пустой результат от Nano Banana."})
        return

    image_bytes = gen_result[0].image_bytes
    if not is_valid_image_bytes(image_bytes):
        await limiter.release_search(user_id_str, user, cost=3)
        await clear_search_pending(redis_client, thread.id)
        yield sse_event("error", {"code": "image_gen_failed",
                                  "message": "Повреждённое изображение от Nano Banana."})
        return

    # ── Persist result ──
    ttl_hours = await resolve_generated_image_ttl_hours(db, redis_client)
    file_id, images_json = await persist_generated_image(
        db, user, image_bytes,
        title=display_content[:200],
        ttl_hours=ttl_hours,
    )

    verb = "объединены" if compose_mode else "отредактировано"
    assistant_text = gen_result[0].assistant_text.strip() or f"Готово — изображение {verb}."

    chunk_size = 24
    for i in range(0, len(assistant_text), chunk_size):
        yield sse_event("token", {"text": assistant_text[i: i + chunk_size]})

    yield sse_event("images", {"images": images_json})

    images_payload = images_json if await messages_have_images_column(db) else None
    assistant_msg = Message(
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=assistant_text,
        images=images_payload,
    )
    db.add(assistant_msg)
    thread.message_count = (thread.message_count or 0) + 2
    thread.last_message_at = datetime.now(timezone.utc)
    await db.commit()

    # Update thread image context for future edits
    await set_thread_image_context(redis_client, thread.id, str(file_id))

    yield sse_event("done", {
        "message_id": str(assistant_msg.id),
        "needs_search": False,
        "answer_model": "pro",
    })
    await clear_search_pending(redis_client, thread.id)
