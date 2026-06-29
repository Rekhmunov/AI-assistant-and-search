"""SSE-поток для конвертации изображений в PDF через Pillow."""
from __future__ import annotations

import io
import json as _json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.message import Message, MessageRole
from app.models.thread import Thread, ThreadType
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.image_compress import format_size, is_image_mime
from app.services.search_pending import clear_search_pending, set_search_pending
from app.services.sse import sse_event
from app.services.upload_storage import load_upload_bytes, save_upload_bytes

logger = logging.getLogger(__name__)

_CONVERTED_TTL_HOURS = 24
_MAX_IMAGES = 10


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


def images_to_pdf_bytes(images_bytes: list[bytes]) -> bytes:
    """
    Конвертирует список изображений в один PDF (одна страница на изображение).
    Использует Pillow — без внешних зависимостей.
    """
    from PIL import Image

    pil_images: list[Image.Image] = []
    for raw in images_bytes:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        pil_images.append(img)

    if not pil_images:
        raise ValueError("Нет изображений для конвертации")

    buf = io.BytesIO()
    first = pil_images[0]
    rest = pil_images[1:]
    first.save(
        buf,
        format="PDF",
        save_all=True,
        append_images=rest,
        resolution=150.0,
    )
    return buf.getvalue()


async def _find_images_in_thread(
    db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> list[UploadedFile]:
    """Ищет последние изображения пользователя в треде."""
    msgs = await db.execute(
        select(Message)
        .where(
            Message.thread_id == thread_id,
            Message.role == MessageRole.USER,
        )
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    found: list[UploadedFile] = []
    for msg in msgs.scalars().all():
        attachments = msg.attachments or []
        if isinstance(attachments, str):
            try:
                attachments = _json.loads(attachments)
            except Exception:
                attachments = []
        for att in (attachments if isinstance(attachments, list) else []):
            if not isinstance(att, dict):
                continue
            file_id_str = att.get("file_id") or att.get("id")
            if not file_id_str:
                continue
            try:
                fid = uuid.UUID(str(file_id_str))
            except ValueError:
                continue
            result = await db.execute(
                select(UploadedFile).where(
                    UploadedFile.id == fid,
                    UploadedFile.user_id == user_id,
                )
            )
            uf = result.scalar_one_or_none()
            if uf and is_image_mime(uf.mime_type or ""):
                found.append(uf)
                if len(found) >= _MAX_IMAGES:
                    return found
        if found:
            return found

    # Fallback: последние изображения за 24 часа
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(UploadedFile)
        .where(
            UploadedFile.user_id == user_id,
            UploadedFile.created_at >= cutoff,
        )
        .order_by(UploadedFile.created_at.desc())
        .limit(_MAX_IMAGES)
    )
    return [uf for uf in result.scalars().all() if is_image_mime(uf.mime_type or "")]


async def stream_image_to_pdf_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
    attachment_ids: list[uuid.UUID] | None = None,
) -> AsyncIterator[str]:
    """SSE-поток: конвертация изображений в PDF."""
    settings = get_settings()

    # ── Найти или создать тред ──
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
        thread = Thread(
            user_id=user.id,
            title=query[:200] or "Конвертация в PDF",
            thread_type=ThreadType.SEARCH,
        )
        db.add(thread)
        await db.flush()

    # ── Собираем изображения из вложений ──
    image_files: list[UploadedFile] = []
    attachments_payload = None

    if attachment_ids:
        attachments_payload = []
        for fid in attachment_ids:
            res = await db.execute(
                select(UploadedFile).where(
                    UploadedFile.id == fid,
                    UploadedFile.user_id == user.id,
                )
            )
            uf = res.scalar_one_or_none()
            attachments_payload.append({
                "id": str(fid),
                "filename": (uf.filename if uf else None) or "image.jpg",
                "kind": "image",
            })
            if uf and is_image_mime(uf.mime_type or ""):
                image_files.append(uf)

    user_msg = Message(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=(query or "").strip() or "Конвертировать в PDF",
        attachments=attachments_payload,
    )
    db.add(user_msg)
    await db.flush()
    await db.commit()

    await set_search_pending(
        redis_client,
        thread.id,
        user_message_id=user_msg.id,
        phase="answering",
        needs_search=False,
        intent="image_to_pdf",
    )

    yield sse_event("thread", {"thread_id": str(thread.id)})
    yield sse_event(
        "route",
        {
            "needs_search": False,
            "answer_model": "lite",
            "reason": "image_to_pdf",
            "intent": "image_to_pdf",
            "policy_version": "v1",
        },
    )

    # Если нет вложений — ищем в истории треда
    if not image_files:
        image_files = await _find_images_in_thread(db, thread.id, user.id)

    if not image_files:
        answer_text = (
            "Не нашёл изображения в этом диалоге. "
            "Прикрепите фото и попросите конвертировать в PDF."
        )
        assistant_msg = Message(
            thread_id=thread.id, role=MessageRole.ASSISTANT, content=answer_text
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        await db.commit()
        for chunk in _chunks(answer_text, 30):
            yield sse_event("token", {"text": chunk})
        yield sse_event(
            "done",
            {"message_id": str(assistant_msg.id), "needs_search": False, "answer_model": "lite"},
        )
        await clear_search_pending(redis_client, thread.id)
        return

    n = len(image_files)
    plural = "фотографию" if n == 1 else f"{n} фотографии"
    status_text = f"Конвертируем {plural} в PDF…"
    for chunk in _chunks(status_text, 40):
        yield sse_event("token", {"text": chunk})

    # Загружаем байты всех изображений
    images_bytes: list[bytes] = []
    filenames: list[str] = []
    for img_file in image_files:
        raw = load_upload_bytes(img_file.storage_key)
        if not raw:
            logger.warning("image_to_pdf: cannot load %s", img_file.filename)
            continue
        images_bytes.append(raw)
        filenames.append(img_file.filename or "image.jpg")

    if not images_bytes:
        answer_text = "Не удалось загрузить изображения. Попробуйте ещё раз."
        assistant_msg = Message(
            thread_id=thread.id, role=MessageRole.ASSISTANT, content=answer_text
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        await db.commit()
        for chunk in _chunks(answer_text, 30):
            yield sse_event("token", {"text": chunk})
        yield sse_event(
            "done",
            {"message_id": str(assistant_msg.id), "needs_search": False, "answer_model": "lite"},
        )
        await clear_search_pending(redis_client, thread.id)
        return

    try:
        pdf_bytes = images_to_pdf_bytes(images_bytes)
    except Exception as exc:
        logger.exception("image_to_pdf failed: %s", exc)
        answer_text = "Не удалось конвертировать изображение в PDF. Попробуйте ещё раз."
        assistant_msg = Message(
            thread_id=thread.id, role=MessageRole.ASSISTANT, content=answer_text
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        await db.commit()
        for chunk in _chunks(answer_text, 30):
            yield sse_event("token", {"text": chunk})
        yield sse_event(
            "done",
            {"message_id": str(assistant_msg.id), "needs_search": False, "answer_model": "lite"},
        )
        await clear_search_pending(redis_client, thread.id)
        return

    # Имя выходного файла
    if len(filenames) == 1:
        stem = filenames[0].rsplit(".", 1)[0] if "." in filenames[0] else filenames[0]
        pdf_name = f"{stem}.pdf"
    else:
        pdf_name = "images.pdf"

    new_file_id = uuid.uuid4()
    storage_key = save_upload_bytes(user.id, new_file_id, pdf_bytes, "pdf")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=_CONVERTED_TTL_HOURS)
    db.add(UploadedFile(
        id=new_file_id,
        user_id=user.id,
        filename=pdf_name,
        mime_type="application/pdf",
        size_bytes=len(pdf_bytes),
        media_kind="converted",
        storage_key=storage_key,
        extracted_text="",
        expires_at=expires_at,
    ))
    await db.flush()

    base_url = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    download_url = f"{base_url}/api/files/{new_file_id}/content"

    pages_label = f"{len(images_bytes)} стр." if len(images_bytes) > 1 else "1 стр."
    result_text = (
        f"\n\n✅ Готово!\n\n**{pdf_name}** — {pages_label}, "
        f"{format_size(len(pdf_bytes))}"
    )
    for chunk in _chunks(result_text, 50):
        yield sse_event("token", {"text": chunk})

    attachments_out = [{
        "id": str(new_file_id),
        "filename": pdf_name,
        "kind": "document",
        "url": download_url,
        "ttl_hours": _CONVERTED_TTL_HOURS,
        "expires_at": expires_at.isoformat(),
    }]

    answer_full = status_text + result_text
    assistant_msg = Message(
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=answer_full,
        attachments=attachments_out,
    )
    db.add(assistant_msg)
    thread.message_count = (thread.message_count or 0) + 2
    thread.last_message_at = datetime.now(timezone.utc)
    await db.commit()

    yield sse_event("document_ready", {
        "file_id": str(new_file_id),
        "filename": pdf_name,
        "download_url": download_url,
        "ttl_hours": _CONVERTED_TTL_HOURS,
        "expires_at": expires_at.isoformat(),
    })

    yield sse_event(
        "done",
        {"message_id": str(assistant_msg.id), "needs_search": False, "answer_model": "lite"},
    )
    await clear_search_pending(redis_client, thread.id)
