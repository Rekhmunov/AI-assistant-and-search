"""PDF → JPG/ZIP конвертация через PyMuPDF.

Логика:
- 1 страница → один JPG
- 2+ страниц → ZIP со всеми страницами
- DPI: 150 (стандарт), 300 (высокое), 72 (низкое)
- Лимит ZIP: max_zip_mb_free / max_zip_mb_pro из настроек
"""
from __future__ import annotations

import io
import logging
import uuid
import zipfile
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.thread import Thread, ThreadType
from app.models.message import Message, MessageRole
from app.models.uploaded_file import UploadedFile
from app.models.user import Plan, User
from app.services.search_pending import clear_search_pending, set_search_pending
from app.services.sse import sse_event
from app.services.upload_lifecycle import resolve_max_zip_mb_free, resolve_max_zip_mb_pro
from app.services.upload_storage import load_upload_bytes, save_upload_bytes
from app.services.pdf_compress import format_size

logger = logging.getLogger(__name__)

_CONVERTED_TTL_HOURS = 24

_DPI_MAP = {
    "high": 300,
    "standard": 150,
    "low": 72,
}


def detect_dpi(text: str) -> int:
    """Определяет DPI из текста запроса."""
    t = (text or "").lower()
    if any(w in t for w in ("высок", "hd", "300", "high", "качеств")):
        return 300
    if any(w in t for w in ("низк", "72", "маленьк", "мал", "low", "small")):
        return 72
    return 150  # стандарт по умолчанию


def pymupdf_available() -> bool:
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


async def _find_pdf_in_thread(
    db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> UploadedFile | None:
    """Ищет последний PDF пользователя в треде (аналог pdf_compress_flow)."""
    import json as _json
    msgs = await db.execute(
        select(Message)
        .where(Message.thread_id == thread_id, Message.role == MessageRole.USER)
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
            res = await db.execute(
                select(UploadedFile).where(UploadedFile.id == fid, UploadedFile.user_id == user_id)
            )
            uf = res.scalar_one_or_none()
            if uf and (uf.mime_type or "").lower() == "application/pdf":
                return uf

    from datetime import timedelta, timezone as _tz
    cutoff = datetime.now(_tz.utc) - timedelta(hours=24)
    res = await db.execute(
        select(UploadedFile)
        .where(
            UploadedFile.user_id == user_id,
            UploadedFile.mime_type == "application/pdf",
            UploadedFile.created_at >= cutoff,
        )
        .order_by(UploadedFile.created_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def stream_pdf_convert_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
    attachment_ids: list[uuid.UUID] | None = None,
) -> AsyncIterator[str]:
    """SSE-поток конвертации PDF → JPG/ZIP."""

    if not pymupdf_available():
        yield sse_event("error", {"code": "convert_unavailable", "message": "Конвертация PDF временно недоступна."})
        return

    settings = get_settings()

    # ── Найти или создать тред ──
    if thread_id:
        res = await db.execute(
            select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id, Thread.deleted_at.is_(None))
        )
        thread = res.scalar_one_or_none()
        if not thread:
            yield sse_event("error", {"code": "not_found", "message": "Тред не найден"})
            return
    else:
        thread = Thread(user_id=user.id, title=query[:200] or "Конвертация PDF", thread_type=ThreadType.SEARCH)
        db.add(thread)
        await db.flush()

    # ── Найти все PDF (поддержка нескольких файлов) ──
    pdf_files: list[UploadedFile] = []
    attachments_payload = None

    if attachment_ids:
        attachments_payload = []
        for fid in attachment_ids:
            res = await db.execute(select(UploadedFile).where(UploadedFile.id == fid, UploadedFile.user_id == user.id))
            uf = res.scalar_one_or_none()
            attachments_payload.append({
                "id": str(fid),
                "filename": (uf.filename if uf else None) or "document.pdf",
                "kind": "document",
            })
            if uf and (uf.mime_type or "").lower() == "application/pdf":
                pdf_files.append(uf)

    pdf_file: UploadedFile | None = pdf_files[0] if pdf_files else None

    user_msg = Message(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=(query or "").strip() or "Конвертировать PDF в JPG",
        attachments=attachments_payload,
    )
    db.add(user_msg)
    await db.flush()
    await db.commit()

    await set_search_pending(redis_client, thread.id, user_message_id=user_msg.id,
                             phase="answering", needs_search=False, intent="convert_pdf")

    yield sse_event("thread", {"thread_id": str(thread.id)})
    yield sse_event("route", {"needs_search": False, "answer_model": "lite",
                              "reason": "convert_pdf", "intent": "convert_pdf", "policy_version": "v1"})

    if not pdf_files:
        found = await _find_pdf_in_thread(db, thread.id, user.id)
        if found:
            pdf_files = [found]
    pdf_file = pdf_files[0] if pdf_files else None

    if not pdf_file or not pdf_files:
        answer_text = "Не нашёл PDF-файл. Загрузите PDF и попросите конвертировать в JPG."
        assistant_msg = Message(thread_id=thread.id, role=MessageRole.ASSISTANT, content=answer_text)
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        await db.commit()
        for chunk in _chunks(answer_text, 40):
            yield sse_event("token", {"text": chunk})
        yield sse_event("done", {"message_id": str(assistant_msg.id), "needs_search": False, "answer_model": "lite"})
        await clear_search_pending(redis_client, thread.id)
        return

    # ── Параметры конвертации ──
    dpi = detect_dpi(query)
    dpi_label = {300: "высокое", 72: "низкое"}.get(dpi, "оптимальное")

    # ── Лимит ZIP ──
    max_zip_mb = await resolve_max_zip_mb_pro(db, redis_client) if user.plan == Plan.PRO else \
        await resolve_max_zip_mb_free(db, redis_client)
    max_zip_bytes = max_zip_mb * 1024 * 1024

    n = len(pdf_files)
    plural = "PDF" if n == 1 else f"{n} PDF"
    status_text = f"Конвертируем {plural} в JPG (качество {dpi_label})"
    for chunk in _chunks(status_text, 40):
        yield sse_event("token", {"text": chunk})

    base_url = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    results: list[dict] = []

    for pdf_file in pdf_files:
        original_bytes = load_upload_bytes(pdf_file.storage_key)
        if not original_bytes:
            results.append({"error": f"Не удалось прочитать «{pdf_file.filename}»"})
            continue
        await _convert_single_pdf(
            db, user, pdf_file, original_bytes, dpi, max_zip_bytes, max_zip_mb,
            base_url, results
        )

    # ── Формируем итоговый текст ──
    result_lines = ["\n\n✅ Готово!"]
    attachments_out = []
    for r in results:
        if "error" in r:
            result_lines.append(f"⚠️ {r['error']}")
        else:
            result_lines.append(
                f"\n**{r['filename']}** ({r['desc']})"
            )
            attachments_out.append({
                "id": r["file_id"], "filename": r["filename"],
                "kind": "document", "url": r["download_url"],
                "ttl_hours": _CONVERTED_TTL_HOURS, "expires_at": r["expires_at"],
            })

    result_text = "\n".join(result_lines) + "\nФайлы хранятся 24 часа."
    for chunk in _chunks(result_text, 50):
        yield sse_event("token", {"text": chunk})

    answer_full = status_text + result_text
    assistant_msg = Message(
        thread_id=thread.id, role=MessageRole.ASSISTANT,
        content=answer_full, attachments=attachments_out or None,
    )
    db.add(assistant_msg)
    thread.message_count = (thread.message_count or 0) + 2
    now = datetime.now(timezone.utc)
    thread.last_message_at = now

    if not thread_id and pdf_files:
        thread.title = f"PDF → JPG · {pdf_files[0].filename or 'файл'}"
    await db.commit()

    for r in results:
        if "error" not in r:
            yield sse_event("document_ready", {
                "file_id": r["file_id"], "filename": r["filename"],
                "download_url": r["download_url"],
                "ttl_hours": _CONVERTED_TTL_HOURS, "expires_at": r["expires_at"],
            })

    yield sse_event("done", {"message_id": str(assistant_msg.id), "needs_search": False, "answer_model": "lite"})
    await clear_search_pending(redis_client, thread.id)


async def _convert_single_pdf(
    db, user, pdf_file: "UploadedFile", original_bytes: bytes,
    dpi: int, max_zip_bytes: int, max_zip_mb: int,
    base_url: str, results: list,
) -> None:
    """Convert one PDF to JPG/ZIP and append result to results list."""
    import fitz
    stem = (pdf_file.filename or "document").rsplit(".", 1)[0]

    try:
        doc = fitz.open(stream=original_bytes, filetype="pdf")
        total_pages = len(doc)
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pages_data: list[tuple[int, bytes]] = []
        total_size = 0

        for page_num in range(total_pages):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
            jpg_bytes = pix.tobytes(output="jpeg", jpg_quality=85)
            if total_size + len(jpg_bytes) > max_zip_bytes:
                if not pages_data:
                    results.append({"error": f"«{pdf_file.filename}» слишком большой (лимит {max_zip_mb} МБ)"})
                    doc.close()
                    return
                break
            pages_data.append((page_num + 1, jpg_bytes))
            total_size += len(jpg_bytes)

        doc.close()
        converted_pages = len(pages_data)
        truncated = converted_pages < total_pages
    except Exception as exc:
        logger.warning("pdf convert failed %s: %s", pdf_file.filename, exc)
        results.append({"error": f"Ошибка конвертации «{pdf_file.filename}»"})
        return

    new_file_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=_CONVERTED_TTL_HOURS)

    if converted_pages == 1:
        _, jpg_bytes = pages_data[0]
        out_filename = f"{stem}.jpg"
        storage_key = save_upload_bytes(user.id, new_file_id, jpg_bytes, "jpg")
        mime_type = "image/jpeg"
        file_size = len(jpg_bytes)
        desc = f"1 стр. → JPG ({format_size(file_size)})"
    else:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for page_num, jpg_bytes in pages_data:
                zf.writestr(f"{stem}_page_{page_num:03d}.jpg", jpg_bytes)
        zip_bytes = buf.getvalue()
        out_filename = f"{stem}_pages.zip"
        storage_key = save_upload_bytes(user.id, new_file_id, zip_bytes, "zip")
        mime_type = "application/zip"
        file_size = len(zip_bytes)
        desc = (
            f"{converted_pages}/{total_pages} стр. → ZIP ({format_size(file_size)})"
            if truncated else
            f"{converted_pages} стр. → ZIP ({format_size(file_size)})"
        )

    db.add(UploadedFile(
        id=new_file_id, user_id=user.id, filename=out_filename,
        mime_type=mime_type, size_bytes=file_size, media_kind="converted",
        storage_key=storage_key, extracted_text="", expires_at=expires_at,
    ))
    await db.flush()
    download_url = f"{base_url}/api/files/{new_file_id}/content"
    results.append({
        "file_id": str(new_file_id), "filename": out_filename,
        "download_url": download_url, "expires_at": expires_at.isoformat(), "desc": desc,
    })


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i: i + size]
