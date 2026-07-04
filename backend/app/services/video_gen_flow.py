"""SSE-поток генерации видео через BytePlus Seedance 2.0."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.message import Message, MessageRole
from app.models.thread import Thread, ThreadType
from app.models.user import Plan, User
from app.services.search_pending import clear_search_pending, set_search_pending, update_search_pending
from app.services.service_incidents import record_service_incident
from app.services.sse import sse_event
from app.services.upload_storage import save_upload_bytes
from app.services.video_gen_service import (
    VideoGenerationError,
    VideoGenerationResult,
    poll_video_task,
    resolve_video_gen_provider_id,
    submit_video_task,
)

logger = logging.getLogger(__name__)

_VIDEO_GEN_COST = 5  # кредитов за генерацию видео

STATUS_MESSAGES = (
    "Отправляем запрос на генерацию…",
    "Видео генерируется, это займёт 1–3 минуты…",
    "Обрабатываем кадры…",
    "Почти готово…",
)
_STATUS_INTERVAL_SEC = 15.0


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


async def stream_video_generation_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
) -> AsyncIterator[str]:
    """SSE-поток генерации видео."""
    settings = get_settings()
    user_id_str = str(user.id)

    if user.plan != Plan.PRO:
        yield sse_event("error", {
            "code": "free_video_gen_pro",
            "message": "Генерация видео доступна только в тарифе Pro.",
        })
        return

    if not settings.byteplus_configured:
        yield sse_event("error", {
            "code": "video_gen_unavailable",
            "message": "Генерация видео не настроена на сервере (BYTEPLUS_API_KEY).",
        })
        return

    allowed, used, limit = await limiter.check_search_limit(
        user_id_str, user.plan, user, cost=_VIDEO_GEN_COST
    )
    if not allowed:
        yield sse_event("error", {
            "code": "video_gen_rate_limit",
            "message": f"Недостаточно кредитов: генерация видео стоит {_VIDEO_GEN_COST} кредитов.",
        })
        return

    # Создаём или загружаем тред
    if thread_id:
        from sqlalchemy import select
        result = await db.execute(
            select(Thread).where(
                Thread.id == thread_id,
                Thread.user_id == user.id,
                Thread.deleted_at.is_(None),
            )
        )
        thread = result.scalar_one_or_none()
        if not thread:
            await limiter.release_search(user_id_str, user, cost=_VIDEO_GEN_COST)
            yield sse_event("error", {"code": "not_found", "message": "Тред не найден"})
            return
    else:
        thread = Thread(
            user_id=user.id,
            title=query[:200] or "Генерация видео",
            thread_type=ThreadType.SEARCH,
        )
        db.add(thread)
        await db.flush()

    display_content = query.strip() or "Сгенерируй видео"
    user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=display_content)
    db.add(user_msg)
    await db.flush()
    await db.commit()

    _thread_id_val = thread.id

    await set_search_pending(
        redis_client, _thread_id_val,
        user_message_id=user_msg.id,
        phase="video_generating",
        needs_search=False,
        intent="video_generate",
        custom_status=STATUS_MESSAGES[0],
    )

    yield sse_event("thread", {"thread_id": str(_thread_id_val)})
    yield sse_event("route", {
        "needs_search": False,
        "answer_model": "pro",
        "reason": "video_generation",
        "intent": "video_generate",
        "policy_version": "v1",
    })
    yield sse_event("video_gen_start", {"status": STATUS_MESSAGES[0]})

    provider_id = await resolve_video_gen_provider_id(db, redis_client)

    # Запускаем генерацию в фоне + отправляем статус-сообщения каждые 15 сек
    gen_result: list[VideoGenerationResult] = []
    gen_error: list[VideoGenerationError] = []
    gen_done = asyncio.Event()

    async def _run_generation() -> None:
        try:
            task_id = await submit_video_task(
                prompt=display_content,
                provider_id=provider_id,
                resolution="720p",
                duration=5,
            )
            result = await poll_video_task(task_id)
            gen_result.append(result)
        except VideoGenerationError as exc:
            gen_error.append(exc)
        finally:
            gen_done.set()

    gen_task = asyncio.create_task(_run_generation())

    status_idx = 1
    while not gen_done.is_set():
        try:
            await asyncio.wait_for(asyncio.shield(gen_done.wait()), timeout=_STATUS_INTERVAL_SEC)
        except asyncio.TimeoutError:
            if status_idx < len(STATUS_MESSAGES):
                msg = STATUS_MESSAGES[status_idx]
                status_idx += 1
                await update_search_pending(redis_client, _thread_id_val, custom_status=msg)
                yield sse_event("video_gen_status", {"status": msg})

    await gen_task

    if gen_error:
        exc = gen_error[0]
        await record_service_incident(redis_client, service="video_gen", kind=exc.code, message=str(exc))
        await limiter.release_search(user_id_str, user, cost=_VIDEO_GEN_COST)
        await clear_search_pending(redis_client, _thread_id_val)
        yield sse_event("error", {"code": "video_gen_failed", "message": "Не удалось сгенерировать видео. Попробуйте ещё раз."})
        return

    result = gen_result[0]

    # Скачиваем видео и сохраняем локально (BytePlus хранит только 24 часа)
    video_file_id: uuid.UUID | None = None
    video_download_url: str = result.video_url
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(result.video_url)
        if resp.is_success and resp.content:
            video_bytes = resp.content
            video_file_id = uuid.uuid4()
            from app.models.uploaded_file import UploadedFile
            storage_key = save_upload_bytes(user.id, video_file_id, video_bytes, "mp4")
            vf = UploadedFile(
                id=video_file_id, user_id=user.id, filename=f"video-{video_file_id.hex[:8]}.mp4",
                mime_type="video/mp4", size_bytes=len(video_bytes),
                media_kind="generated", storage_key=storage_key, extracted_text="",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
            )
            db.add(vf)
            await db.flush()
            base_url = (settings.public_web_url or "https://glosix.ru").rstrip("/")
            video_download_url = f"{base_url}/api/files/{video_file_id}/content"
            logger.info("video_gen: saved locally file_id=%s", video_file_id)
    except Exception as exc:
        logger.warning("video_gen: failed to save video locally, using direct URL: %s", exc)

    answer_text = f"Видео сгенерировано. Нажмите для просмотра или скачайте."
    for chunk in _chunks(answer_text, 40):
        yield sse_event("token", {"text": chunk})

    video_payload = {
        "video_url": video_download_url,
        "original_url": result.video_url,
        "cover_url": result.cover_image_url,
        "duration": result.duration,
        "resolution": result.resolution,
        "file_id": str(video_file_id) if video_file_id else None,
    }
    yield sse_event("video_ready", video_payload)

    from app.services.message_images_column import messages_have_images_column
    images_payload = None
    if video_file_id and await messages_have_images_column(db):
        images_payload = [{"url": video_download_url, "title": "Сгенерированное видео", "page_url": video_download_url}]

    assistant_msg = Message(
        thread_id=thread.id, role=MessageRole.ASSISTANT, content=answer_text,
        images=images_payload,
    )
    db.add(assistant_msg)
    thread.message_count = (thread.message_count or 0) + 2
    thread.last_message_at = datetime.now(timezone.utc)
    if not thread_id:
        thread.title = display_content[:200]
    await db.commit()

    yield sse_event("done", {
        "message_id": str(assistant_msg.id),
        "needs_search": False,
        "answer_model": "pro",
        "searches_today": used,
        "searches_limit": limit,
    })
    await clear_search_pending(redis_client, _thread_id_val)
