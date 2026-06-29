"""SSE-поток для разбивки PDF на части через pypdf."""
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
from app.models.user import Plan
from app.services.pdf_compress import format_size
from app.services.pdf_split import build_split_zip, detect_split_params, split_pdf_bytes
from app.services.search_pending import clear_search_pending, set_search_pending
from app.services.sse import sse_event
from app.services.upload_lifecycle import resolve_max_upload_mb_free, resolve_max_upload_mb_pro
from app.services.upload_storage import load_upload_bytes, save_upload_bytes

logger = logging.getLogger(__name__)

_SPLIT_TTL_HOURS = 24
_MAX_PAGES = 2000   # защита от слишком больших PDF
_MAX_PARTS = 500    # защита от слишком мелкой нарезки


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


async def _find_pdf_in_thread(
    db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> UploadedFile | None:
    """Ищет последний PDF пользователя в треде."""
    msgs = await db.execute(
        select(Message)
        .where(
            Message.thread_id == thread_id,
            Message.role == MessageRole.USER,
        )
        .order_by(Message.created_at.desc())
        .limit(10)
    )
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
            if uf and (uf.mime_type or "").lower() == "application/pdf":
                return uf

    # Fallback: последний PDF за 24 часа
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(UploadedFile)
        .where(
            UploadedFile.user_id == user_id,
            UploadedFile.mime_type == "application/pdf",
            UploadedFile.created_at >= cutoff,
        )
        .order_by(UploadedFile.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def stream_pdf_split_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
    attachment_ids: list[uuid.UUID] | None = None,
) -> AsyncIterator[str]:
    """SSE-поток: разбивка PDF на части."""
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
            title=query[:200] or "Разбивка PDF",
            thread_type=ThreadType.SEARCH,
        )
        db.add(thread)
        await db.flush()

    # ── Найти PDF во вложениях или треде ──
    pdf_file: UploadedFile | None = None
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
                "filename": (uf.filename if uf else None) or "document.pdf",
                "kind": "document",
            })
            if uf and (uf.mime_type or "").lower() == "application/pdf" and pdf_file is None:
                pdf_file = uf

    user_msg = Message(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=(query or "").strip() or "Разбить PDF",
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
        intent="split_pdf",
    )

    yield sse_event("thread", {"thread_id": str(thread.id)})
    yield sse_event(
        "route",
        {
            "needs_search": False,
            "answer_model": "lite",
            "reason": "split_pdf",
            "intent": "split_pdf",
            "policy_version": "v1",
        },
    )

    # Если нет вложений — ищем в истории
    if not pdf_file:
        pdf_file = await _find_pdf_in_thread(db, thread.id, user.id)

    if not pdf_file:
        answer_text = (
            "Не нашёл PDF-файл в этом диалоге. "
            "Загрузите PDF и попросите разбить."
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

    # ── Проверка размера входного PDF по тарифу ──
    max_mb = (
        await resolve_max_upload_mb_pro(db, redis_client)
        if user.plan == Plan.PRO
        else await resolve_max_upload_mb_free(db, redis_client)
    )
    max_bytes = max_mb * 1024 * 1024
    if pdf_file.size_bytes and pdf_file.size_bytes > max_bytes:
        answer_text = (
            f"PDF слишком большой для разбивки: {format_size(pdf_file.size_bytes)}. "
            f"Максимальный размер для вашего тарифа — {max_mb} МБ."
        )
        assistant_msg = Message(
            thread_id=thread.id, role=MessageRole.ASSISTANT, content=answer_text
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        await db.commit()
        for chunk in _chunks(answer_text, 50):
            yield sse_event("token", {"text": chunk})
        yield sse_event(
            "done",
            {"message_id": str(assistant_msg.id), "needs_search": False, "answer_model": "lite"},
        )
        await clear_search_pending(redis_client, thread.id)
        return

    # Загружаем PDF
    original_bytes = load_upload_bytes(pdf_file.storage_key)
    if not original_bytes:
        answer_text = "Не удалось загрузить PDF. Попробуйте загрузить файл заново."
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

    # Определяем параметры разбивки
    params = detect_split_params(query)

    # Статус
    if "pages_per_file" in params:
        ppf = params["pages_per_file"]
        status_text = (
            f"Разбиваем PDF по {ppf} стр. на файл…"
            if ppf > 1
            else "Разбиваем PDF на отдельные страницы…"
        )
    else:
        status_text = f"Разбиваем PDF на {params['n_parts']} части…"

    for chunk in _chunks(status_text, 40):
        yield sse_event("token", {"text": chunk})

    # Выполняем разбивку
    try:
        parts = split_pdf_bytes(original_bytes, **params)
    except Exception as exc:
        logger.exception("pdf split failed: %s", exc)
        answer_text = f"Не удалось разбить PDF: {exc}"
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

    # Защита от слишком большого количества частей
    if len(parts) > _MAX_PARTS:
        parts = parts[:_MAX_PARTS]
        logger.warning("pdf split: capped at %d parts", _MAX_PARTS)

    n_parts = len(parts)
    stem = (pdf_file.filename or "document").rsplit(".", 1)[0]

    base_url = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=_SPLIT_TTL_HOURS)

    # Если одна часть — отдаём PDF напрямую, иначе ZIP
    if n_parts == 1:
        only_name, only_bytes = parts[0]
        new_file_id = uuid.uuid4()
        storage_key = save_upload_bytes(user.id, new_file_id, only_bytes, "pdf")
        db.add(UploadedFile(
            id=new_file_id, user_id=user.id, filename=only_name,
            mime_type="application/pdf", size_bytes=len(only_bytes),
            media_kind="converted", storage_key=storage_key,
            extracted_text="", expires_at=expires_at,
        ))
        await db.flush()
        download_url = f"{base_url}/api/files/{new_file_id}/content"

        result_text = f"\n\n✅ Готово!\n\n**{only_name}** — {format_size(len(only_bytes))}"
        for chunk in _chunks(result_text, 50):
            yield sse_event("token", {"text": chunk})

        attachments_out = [{
            "id": str(new_file_id), "filename": only_name,
            "kind": "document", "url": download_url,
            "ttl_hours": _SPLIT_TTL_HOURS, "expires_at": expires_at.isoformat(),
        }]
        answer_full = status_text + result_text
        assistant_msg = Message(
            thread_id=thread.id, role=MessageRole.ASSISTANT,
            content=answer_full, attachments=attachments_out,
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        await db.commit()
        yield sse_event("document_ready", {
            "file_id": str(new_file_id), "filename": only_name,
            "download_url": download_url,
            "ttl_hours": _SPLIT_TTL_HOURS, "expires_at": expires_at.isoformat(),
        })

    else:
        # Несколько частей → ZIP
        zip_bytes = build_split_zip(parts)
        zip_name = f"{stem}_split_{n_parts}parts.zip"

        new_file_id = uuid.uuid4()
        storage_key = save_upload_bytes(user.id, new_file_id, zip_bytes, "zip")
        db.add(UploadedFile(
            id=new_file_id, user_id=user.id, filename=zip_name,
            mime_type="application/zip", size_bytes=len(zip_bytes),
            media_kind="compressed", storage_key=storage_key,
            extracted_text="", expires_at=expires_at,
        ))
        await db.flush()
        download_url = f"{base_url}/api/files/{new_file_id}/content"

        # Список файлов внутри архива
        file_list = "\n".join(f"  • {name}" for name, _ in parts[:20])
        if n_parts > 20:
            file_list += f"\n  … и ещё {n_parts - 20} файлов"

        result_text = (
            f"\n\n✅ Готово! Разбито на **{n_parts} файлов** → ZIP-архив "
            f"{format_size(len(zip_bytes))}\n\n{file_list}"
        )
        for chunk in _chunks(result_text, 50):
            yield sse_event("token", {"text": chunk})

        attachments_out = [{
            "id": str(new_file_id), "filename": zip_name,
            "kind": "document", "url": download_url,
            "ttl_hours": _SPLIT_TTL_HOURS, "expires_at": expires_at.isoformat(),
        }]
        answer_full = status_text + result_text
        assistant_msg = Message(
            thread_id=thread.id, role=MessageRole.ASSISTANT,
            content=answer_full, attachments=attachments_out,
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        await db.commit()
        yield sse_event("document_ready", {
            "file_id": str(new_file_id), "filename": zip_name,
            "download_url": download_url,
            "ttl_hours": _SPLIT_TTL_HOURS, "expires_at": expires_at.isoformat(),
        })

    yield sse_event(
        "done",
        {"message_id": str(assistant_msg.id), "needs_search": False, "answer_model": "lite"},
    )
    await clear_search_pending(redis_client, thread.id)
