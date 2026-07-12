"""SSE-флоу агента «Сканер документов»: фото → PDF."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.sse import sse_event
from app.services.upload_storage import save_upload_bytes

logger = logging.getLogger(__name__)


async def stream_scan_document_turn(
    db: AsyncSession,
    user: User,
    attachment_ids: list[uuid.UUID],
    thread_id: uuid.UUID | None,
    redis_client,
    query: str = "",
) -> AsyncIterator[str]:
    """SSE-поток: загружает фото из вложений, обрабатывает, возвращает PDF."""
    from sqlalchemy import select
    from app.models.uploaded_file import UploadedFile
    from app.models.message import Message, MessageRole
    from app.models.thread import Thread, ThreadType
    from app.services.scan_document_service import scan_images_to_pdf, ScanError
    from app.services.upload_storage import load_upload_bytes

    if not attachment_ids:
        yield sse_event("error", {
            "code": "no_attachments",
            "message": "Прикрепите одно или несколько фото документа.",
        })
        return

    # Проверяем вложения
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id.in_(attachment_ids),
            UploadedFile.user_id == user.id,
        )
    )
    files_by_id = {str(f.id): f for f in result.scalars().all()}
    # Сохраняем порядок из attachment_ids
    files = [files_by_id[str(aid)] for aid in attachment_ids if str(aid) in files_by_id]
    image_files = [f for f in files if (f.mime_type or "").startswith("image/")]

    if not image_files:
        yield sse_event("error", {
            "code": "no_images",
            "message": "Нужно приложить фотографии документа (JPEG, PNG, HEIC).",
        })
        return

    # Создаём или загружаем тред
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
    yield sse_event("route", {"needs_search": False, "answer_model": "lite", "reason": "scan_document"})
    yield sse_event("token", {"text": f"Обрабатываю {len(image_files)} фото…"})

    # Загружаем байты изображений
    images_bytes: list[bytes] = []
    for f in image_files:
        raw = load_upload_bytes(f.storage_key)
        if raw:
            images_bytes.append(raw)

    if not images_bytes:
        yield sse_event("error", {"code": "load_error", "message": "Не удалось загрузить изображения."})
        return

    # Если это агент-сканер — активируем и снимаем is_new (тред появится в истории)
    if thread_id:
        from sqlalchemy import select as _sel2
        from app.models.agent import AgentInstance as _AI2, AgentStatus as _AS2
        from sqlalchemy.orm.attributes import flag_modified as _fm2
        _ar = await db.execute(_sel2(_AI2).where(_AI2.thread_id == thread_id, _AI2.user_id == user.id))
        _ag = _ar.scalar_one_or_none()
        if _ag and (_ag.config or {}).get("template") == "scanner":
            _cfg2 = dict(_ag.config or {})
            _cfg2.pop("is_new", None)
            _ag.config = _cfg2
            _fm2(_ag, "config")
            if _ag.status in (_AS2.DRAFT.value, _AS2.COLLECTING.value, "draft", "collecting"):
                _ag.status = _AS2.ACTIVE.value

    # Запускаем обработку в thread executor (CPU-intensive)
    yield sse_event("token", {"text": "\nВыравниваю и улучшаю качество…"})

    loop = asyncio.get_event_loop()
    try:
        scan_result = await loop.run_in_executor(
            None, scan_images_to_pdf, images_bytes
        )
    except ScanError as exc:
        yield sse_event("error", {"code": exc.code, "message": str(exc)})
        return
    except Exception as exc:
        logger.exception("scan_document_flow error")
        yield sse_event("error", {"code": "scan_failed", "message": "Ошибка при обработке изображения."})
        return

    yield sse_event("token", {"text": "\nУпаковываю в PDF…"})

    # Сохраняем PDF
    file_id = uuid.uuid4()
    storage_key = save_upload_bytes(user.id, file_id, scan_result.pdf_bytes, "pdf")

    from app.models.uploaded_file import UploadedFile as UF
    from app.core.config import get_settings
    settings = get_settings()

    filename = f"scan_{file_id.hex[:8]}.pdf"
    out_file = UF(
        id=file_id,
        user_id=user.id,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=len(scan_result.pdf_bytes),
        media_kind="generated_doc",
        storage_key=storage_key,
        extracted_text="",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
    )
    db.add(out_file)
    await db.flush()

    base_url = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    download_url = f"{base_url}/api/files/{file_id}/content"

    summary = (
        f"\n✅ Готово! PDF создан: {scan_result.page_count} стр., "
        f"{scan_result.output_size_kb} КБ "
        f"(исходные фото: {scan_result.original_size_kb} КБ)"
    )
    yield sse_event("token", {"text": summary})

    # Сохраняем ответ ассистента с вложением в стандартном формате
    from app.models.message import Message, MessageRole
    assistant_msg = Message(
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=f"Обработал {scan_result.page_count} стр. → PDF {scan_result.output_size_kb} КБ",
        attachments=[{
            "id": str(file_id),
            "filename": filename,
            "kind": "document",
            "url": download_url,
            "size_kb": scan_result.output_size_kb,
        }],
    )
    db.add(assistant_msg)
    thread.message_count = (thread.message_count or 0) + 2
    thread.last_message_at = datetime.now(timezone.utc)
    await db.commit()

    # document_ready — стандартный ивент для документов (как в pdf_compress_flow)
    yield sse_event("document_ready", {
        "file_id": str(file_id),
        "filename": filename,
        "download_url": download_url,
        "size_kb": scan_result.output_size_kb,
        "pages": scan_result.page_count,
    })
    yield sse_event("done", {
        "message_id": str(assistant_msg.id),
        "needs_search": False,
        "answer_model": "lite",
    })
