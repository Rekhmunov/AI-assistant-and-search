"""
SSE-флоу агента «Сканер документов»: фото → PDF через AI.
Тарификация: как генерация картинок (check_image_gen_limit / release_image_gen).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Plan, User
from app.services.sse import sse_event

logger = logging.getLogger(__name__)


async def stream_scan_document_turn(
    db: AsyncSession,
    user: User,
    attachment_ids: list[uuid.UUID],
    thread_id: uuid.UUID | None,
    redis_client,
    query: str = "",
) -> AsyncIterator[str]:
    """SSE-поток: загружает фото из вложений, обрабатывает через AI, возвращает PDF."""
    from sqlalchemy import select
    from app.models.uploaded_file import UploadedFile
    from app.models.message import Message, MessageRole
    from app.models.thread import Thread, ThreadType
    from app.core.config import get_settings
    from app.core.limiter import RateLimiter
    from app.services.scan_document_service import (
        ScanError, images_to_pdf, compress_pdf, process_image_with_ai,
    )
    from app.services.upload_storage import load_upload_bytes, save_upload_bytes

    settings = get_settings()
    # (get_rate_limiter не используется — лимитер создаётся напрямую ниже)

    if not attachment_ids:
        yield sse_event("error", {
            "code": "no_attachments",
            "message": "Прикрепите одно или несколько фото документа.",
        })
        return

    # ── Проверяем лимит (как для генерации картинок) ───────────────────────
    limiter = RateLimiter(redis_client)
    user_id_str = str(user.id)

    if user.plan != Plan.PRO:
        # Free-пользователи — check_image_gen_limit
        allowed, used, limit = await limiter.check_image_gen_limit(user_id_str, user.plan)
        if not allowed:
            yield sse_event("error", {
                "code": "free_image_gen_pro",
                "message": (
                    "Сканирование документов доступно только в тарифе Pro. "
                    "Перейдите на Pro для работы с ИИ-сканером."
                ),
            })
            return
    else:
        # Pro — списываем как 1K картинку (3 кредита)
        allowed, used, limit = await limiter.check_search_limit(user_id_str, user.plan, user, cost=3)
        if not allowed:
            yield sse_event("error", {
                "code": "image_gen_rate_limit",
                "message": f"Лимит Pro исчерпан. Попробуйте завтра (лимит: {limit} в день).",
            })
            return

    # ── Проверяем вложения ─────────────────────────────────────────────────
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id.in_(attachment_ids),
            UploadedFile.user_id == user.id,
        )
    )
    files_by_id = {str(f.id): f for f in result.scalars().all()}
    files = [files_by_id[str(aid)] for aid in attachment_ids if str(aid) in files_by_id]
    image_files = [f for f in files if (f.mime_type or "").startswith("image/")]

    if not image_files:
        await _release_limit(limiter, user, user_id_str)
        yield sse_event("error", {
            "code": "no_images",
            "message": "Нужно приложить фотографии документа (JPEG, PNG).",
        })
        return

    # ── Создаём тред если нужно ────────────────────────────────────────────
    if thread_id:
        tr = await db.execute(
            select(Thread).where(
                Thread.id == thread_id,
                Thread.user_id == user.id,
                Thread.deleted_at.is_(None),
            )
        )
        thread = tr.scalar_one_or_none()
        if not thread:
            await _release_limit(limiter, user, user_id_str)
            yield sse_event("error", {"code": "not_found", "message": "Тред не найден"})
            return
    else:
        thread = Thread(
            user_id=user.id,
            title=f"Сканирование — {len(image_files)} стр.",
            thread_type=ThreadType.SEARCH,
        )
        db.add(thread)
        await db.flush()

    display_query = query.strip() or f"Сканировать {len(image_files)} фото"
    user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=display_query)
    db.add(user_msg)
    await db.flush()
    await db.commit()
    _thread_id = thread.id

    yield sse_event("thread", {"thread_id": str(_thread_id)})
    yield sse_event("route", {"needs_search": False, "answer_model": "pro", "reason": "scan_document"})

    # ── Активируем агент-сканер если нужно ────────────────────────────────
    if thread_id:
        from sqlalchemy import select as _sel
        from app.models.agent import AgentInstance as _AI, AgentStatus as _AS
        from sqlalchemy.orm.attributes import flag_modified as _fm
        _ar = await db.execute(_sel(_AI).where(_AI.thread_id == thread_id, _AI.user_id == user.id))
        _ag = _ar.scalar_one_or_none()
        if _ag and (_ag.config or {}).get("template") == "scanner":
            _cfg = dict(_ag.config or {})
            _cfg.pop("is_new", None)
            _ag.config = _cfg
            _fm(_ag, "config")
            if _ag.status in (_AS.DRAFT.value, _AS.COLLECTING.value, "draft", "collecting"):
                _ag.status = _AS.ACTIVE.value
            await db.commit()  # тред появится в истории даже при ошибке скана

    # ── Загружаем байты изображений ────────────────────────────────────────
    images_bytes: list[bytes] = []
    for f in image_files:
        raw = load_upload_bytes(f.storage_key)
        if raw:
            images_bytes.append(raw)

    if not images_bytes:
        await _release_limit(limiter, user, user_id_str)
        yield sse_event("error", {"code": "load_error", "message": "Не удалось загрузить изображения."})
        return

    # ── Обработка через AI ─────────────────────────────────────────────────
    total_pages = len(images_bytes)
    yield sse_event("token", {"text": f"Обрабатываю {total_pages} фото через ИИ…"})

    processed_images: list[bytes] = []
    original_total = sum(len(b) for b in images_bytes)

    for i, img_bytes in enumerate(images_bytes):
        if total_pages > 1:
            yield sse_event("token", {"text": f"\nСтраница {i+1}/{total_pages}…"})
        try:
            processed = await process_image_with_ai(
                img_bytes, settings=settings
            )
            processed_images.append(processed)
        except ScanError as exc:
            await _release_limit(limiter, user, user_id_str)
            yield sse_event("error", {"code": exc.code, "message": str(exc)})
            return
        except Exception as exc:
            logger.exception("scan_document_flow: AI processing failed")
            await _release_limit(limiter, user, user_id_str)
            yield sse_event("error", {"code": "scan_failed", "message": "Ошибка при обработке изображения."})
            return

    yield sse_event("token", {"text": "\nУпаковываю в PDF…"})

    # ── Упаковка в PDF ─────────────────────────────────────────────────────
    try:
        pdf_bytes = images_to_pdf(processed_images)
        try:
            pdf_bytes = compress_pdf(pdf_bytes)
        except Exception:
            pass  # при ошибке компрессии используем несжатый
    except Exception as exc:
        logger.exception("scan_document_flow: PDF creation failed")
        await _release_limit(limiter, user, user_id_str)
        yield sse_event("error", {"code": "pdf_failed", "message": "Не удалось создать PDF."})
        return

    # ── Сохраняем PDF ──────────────────────────────────────────────────────
    file_id = uuid.uuid4()
    filename = f"scan_{file_id.hex[:8]}.pdf"
    storage_key = save_upload_bytes(user.id, file_id, pdf_bytes, "pdf")

    from app.models.uploaded_file import UploadedFile as UF
    out_file = UF(
        id=file_id, user_id=user.id, filename=filename,
        mime_type="application/pdf", size_bytes=len(pdf_bytes),
        media_kind="generated_doc", storage_key=storage_key,
        extracted_text="",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
    )
    db.add(out_file)
    await db.flush()

    base_url = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    download_url = f"{base_url}/api/files/{file_id}/content"

    output_kb = len(pdf_bytes) // 1024
    summary = (
        f"\n✅ Готово! PDF создан: {total_pages} стр., {output_kb} КБ"
    )
    yield sse_event("token", {"text": summary})

    from app.models.message import Message, MessageRole
    assistant_msg = Message(
        thread_id=thread.id, role=MessageRole.ASSISTANT,
        content=f"Обработал {total_pages} стр. через ИИ → PDF {output_kb} КБ",
        attachments=[{
            "id": str(file_id), "filename": filename,
            "kind": "document", "url": download_url, "size_kb": output_kb,
        }],
    )
    db.add(assistant_msg)
    thread.message_count = (thread.message_count or 0) + 2
    thread.last_message_at = datetime.now(timezone.utc)
    await db.commit()

    yield sse_event("document_ready", {
        "file_id": str(file_id), "filename": filename,
        "download_url": download_url, "size_kb": output_kb, "pages": total_pages,
    })
    yield sse_event("done", {
        "message_id": str(assistant_msg.id),
        "needs_search": False, "answer_model": "pro",
    })


async def _release_limit(limiter, user, user_id_str: str) -> None:
    """Возвращает списанный кредит при ошибке."""
    try:
        if user.plan == Plan.PRO:
            await limiter.release_search(user_id_str, user, cost=3)
        else:
            await limiter.release_image_gen(user_id_str)
    except Exception:
        pass
