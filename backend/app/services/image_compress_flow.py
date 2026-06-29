"""SSE-поток для сжатия изображений через Pillow."""
from __future__ import annotations

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
from app.services.image_compress import (
    compress_image_bytes,
    detect_compress_level,
    format_size,
    is_image_mime,
    _LEVEL_LABELS,
)
from app.services.search_pending import clear_search_pending, set_search_pending
from app.services.sse import sse_event
from app.services.upload_storage import load_upload_bytes, save_upload_bytes

logger = logging.getLogger(__name__)

_COMPRESSED_TTL_HOURS = 24
_MAX_IMAGES = 5


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


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


async def stream_image_compress_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
    attachment_ids: list[uuid.UUID] | None = None,
) -> AsyncIterator[str]:
    """SSE-поток: сжатие изображений."""
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
            title=query[:200] or "Сжатие изображения",
            thread_type=ThreadType.SEARCH,
        )
        db.add(thread)
        await db.flush()

    # ── Собираем изображения из вложений текущего запроса ──
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
        content=(query or "").strip() or "Сжать изображение",
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
        intent="compress_image",
    )

    yield sse_event("thread", {"thread_id": str(thread.id)})
    yield sse_event(
        "route",
        {
            "needs_search": False,
            "answer_model": "lite",
            "reason": "compress_image",
            "intent": "compress_image",
            "policy_version": "v1",
        },
    )

    # Если нет вложений — ищем в истории треда
    if not image_files:
        image_files = await _find_images_in_thread(db, thread.id, user.id)

    if not image_files:
        answer_text = (
            "Не нашёл изображение в этом диалоге. "
            "Прикрепите фото и попросите сжать."
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

    level = detect_compress_level(query)
    level_label = _LEVEL_LABELS.get(level, level)
    n = len(image_files)
    plural = "изображение" if n == 1 else f"{n} изображения"
    status_text = f"Сжимаем {plural} (сжатие: {level_label})…"
    for chunk in _chunks(status_text, 40):
        yield sse_event("token", {"text": chunk})

    base_url = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    results: list[dict] = []

    for img_file in image_files:
        original_bytes = load_upload_bytes(img_file.storage_key)
        if not original_bytes:
            results.append({"error": f"Не удалось прочитать «{img_file.filename}»"})
            continue
        try:
            compressed_bytes, out_mime = compress_image_bytes(original_bytes, level)
        except Exception as exc:
            logger.warning("image compress failed %s: %s", img_file.filename, exc)
            results.append({"error": f"Ошибка сжатия «{img_file.filename}»"})
            continue

        orig_size = len(original_bytes)
        comp_size = len(compressed_bytes)
        reduction = int((1 - comp_size / max(orig_size, 1)) * 100)

        new_file_id = uuid.uuid4()
        original_name = img_file.filename or "image.jpg"
        stem = original_name.rsplit(".", 1)[0] if "." in original_name else original_name
        compressed_name = f"{stem}_compressed.jpg"

        storage_key = save_upload_bytes(user.id, new_file_id, compressed_bytes, "jpg")
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=_COMPRESSED_TTL_HOURS)
        db.add(UploadedFile(
            id=new_file_id,
            user_id=user.id,
            filename=compressed_name,
            mime_type="image/jpeg",
            size_bytes=comp_size,
            media_kind="compressed",
            storage_key=storage_key,
            extracted_text="",
            expires_at=expires_at,
        ))
        await db.flush()

        download_url = f"{base_url}/api/files/{new_file_id}/content"
        results.append({
            "file_id": str(new_file_id),
            "filename": compressed_name,
            "download_url": download_url,
            "expires_at": expires_at.isoformat(),
            "orig_size": orig_size,
            "comp_size": comp_size,
            "reduction": reduction,
        })

    result_lines = ["\n\n✅ Готово!"]
    attachments_out = []
    for r in results:
        if "error" in r:
            result_lines.append(f"⚠️ {r['error']}")
        else:
            sign = "-" if r["reduction"] >= 0 else "+"
            result_lines.append(
                f"\n**{r['filename']}**\n"
                f"{format_size(r['orig_size'])} → {format_size(r['comp_size'])} "
                f"({sign}{abs(r['reduction'])}%)"
            )
            attachments_out.append({
                "id": r["file_id"],
                "filename": r["filename"],
                "kind": "image",
                "url": r["download_url"],
                "ttl_hours": _COMPRESSED_TTL_HOURS,
                "expires_at": r["expires_at"],
            })

    result_text = "\n".join(result_lines)
    for chunk in _chunks(result_text, 50):
        yield sse_event("token", {"text": chunk})

    answer_full = status_text + result_text
    assistant_msg = Message(
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=answer_full,
        attachments=attachments_out or None,
    )
    db.add(assistant_msg)
    thread.message_count = (thread.message_count or 0) + 2
    thread.last_message_at = datetime.now(timezone.utc)
    await db.commit()

    for r in results:
        if "error" not in r:
            yield sse_event("document_ready", {
                "file_id": r["file_id"],
                "filename": r["filename"],
                "download_url": r["download_url"],
                "ttl_hours": _COMPRESSED_TTL_HOURS,
                "expires_at": r["expires_at"],
            })

    yield sse_event(
        "done",
        {"message_id": str(assistant_msg.id), "needs_search": False, "answer_model": "lite"},
    )
    await clear_search_pending(redis_client, thread.id)
