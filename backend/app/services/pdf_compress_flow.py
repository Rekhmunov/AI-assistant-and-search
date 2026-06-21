"""SSE-поток для сжатия PDF — двухшаговый диалог.

Шаг 1: пользователь загрузил PDF → спрашиваем уровень сжатия (3 follow-up кнопки).
Шаг 2: пользователь выбрал уровень → сжимаем PDF из истории треда.
"""
from __future__ import annotations

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
from app.services.pdf_compress import (
    compress_pdf_bytes,
    detect_compression_level,
    format_size,
    ghostscript_available,
    has_explicit_compression_level,
)
from app.services.search_pending import clear_search_pending, set_search_pending
from app.services.sse import sse_event
from app.services.upload_storage import load_upload_bytes, save_upload_bytes

logger = logging.getLogger(__name__)

_LEVEL_LABELS = {
    "screen": "Максимальное (меньший размер файла)",
    "ebook": "Оптимальное (рекомендуется)",
    "printer": "Минимальное (лучшее качество)",
}

_COMPRESSED_TTL_HOURS = 24


async def _find_pdf_in_thread(
    db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> UploadedFile | None:
    """
    Ищет последний PDF пользователя в треде.
    Стратегия 1: ищем file_id в attachments пользовательских сообщений треда.
    Стратегия 2: ищем последний PDF в UploadedFile пользователя (fallback).
    """
    import json as _json

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

    # Fallback: последний PDF этого пользователя, загруженный не более 24 часов назад
    from datetime import timedelta, timezone as _tz
    cutoff = datetime.now(_tz.utc) - timedelta(hours=24)
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


async def stream_pdf_compress_turn(
    db: AsyncSession,
    user: User,
    limiter: RateLimiter,
    query: str,
    thread_id: uuid.UUID | None,
    redis_client,
    attachment_ids: list[uuid.UUID] | None = None,
) -> AsyncIterator[str]:
    """
    SSE-поток для compress_pdf flow.

    Шаг 1 (attachment_ids не пуст и содержит PDF) → спросить уровень.
    Шаг 2 (нет вложений, но тред содержит PDF из предыдущего хода) → сжать.
    """
    settings = get_settings()
    user_id_str = str(user.id)

    if not ghostscript_available():
        yield sse_event(
            "error",
            {"code": "compress_unavailable", "message": "Сжатие PDF временно недоступно."},
        )
        return

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
            title=query[:200] or "Сжатие PDF",
            thread_type=ThreadType.SEARCH,
        )
        db.add(thread)
        await db.flush()

    # ── Определяем шаг ДО создания user_msg чтобы получить filename ──
    has_pdf_attachment = False
    pdf_file: UploadedFile | None = None

    if attachment_ids:
        for fid in attachment_ids:
            res = await db.execute(
                select(UploadedFile).where(
                    UploadedFile.id == fid,
                    UploadedFile.user_id == user.id,
                )
            )
            uf = res.scalar_one_or_none()
            if uf and (uf.mime_type or "").lower() == "application/pdf":
                has_pdf_attachment = True
                pdf_file = uf
                break

    # Сохраняем вложения с filename — обязательное поле MessageAttachmentOut
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
            uf_any = res.scalar_one_or_none()
            attachments_payload.append({
                "id": str(fid),
                "filename": (uf_any.filename if uf_any else None) or "document.pdf",
                "kind": "document",
            })

    user_msg = Message(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=(query or "").strip() or "Сжать PDF",
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
        intent="compress_pdf",
    )

    yield sse_event("thread", {"thread_id": str(thread.id)})
    yield sse_event(
        "route",
        {
            "needs_search": False,
            "answer_model": "lite",
            "reason": "compress_pdf",
            "intent": "compress_pdf",
            "policy_version": "v1",
        },
    )

    if has_pdf_attachment and pdf_file:
        file_size_str = format_size(pdf_file.size_bytes or 0)

        # Если уровень уже указан в запросе — сразу сжимаем без переспроса
        if has_explicit_compression_level(query):
            level = detect_compression_level(query)
            # Передаём управление шагу сжатия (ниже)
            pass
        else:
            # ── ШАГ 1: спрашиваем уровень — список вариантов прямо в тексте ──
            answer_text = (
                f"PDF загружен ({file_size_str}). Выберите уровень сжатия:\n"
                "Максимальное (меньший размер файла)\n"
                "Оптимальное (рекомендуется)\n"
                "Минимальное (лучшее качество)"
            )

            assistant_msg = Message(
                thread_id=thread.id,
                role=MessageRole.ASSISTANT,
                content=answer_text,
                # follow_up_questions намеренно не задаём → не показывается блок «Продолжить тему»
            )
            db.add(assistant_msg)
            thread.message_count = (thread.message_count or 0) + 2
            thread.last_message_at = datetime.now(timezone.utc)
            if not thread_id:
                thread.title = f"Сжатие PDF · {pdf_file.filename or 'файл'}"
            await db.commit()

            for chunk in _chunks(answer_text, 40):
                yield sse_event("token", {"text": chunk})

            yield sse_event(
                "done",
                {
                    "message_id": str(assistant_msg.id),
                    "needs_search": False,
                    "answer_model": "lite",
                },
            )
            await clear_search_pending(redis_client, thread.id)
            return

    # ── ШАГ 2: сжимаем ──
    # Попадаем сюда если:
    # а) нет вложений — пользователь ответил уровнем на вопрос
    # б) вложение есть И уровень уже указан в исходном запросе
    level = detect_compression_level(query)

    # pdf_file уже найден если пришёл с вложением; иначе ищем в истории треда
    if not pdf_file:
        pdf_file = await _find_pdf_in_thread(db, thread.id, user.id)
        if not pdf_file:
            answer_text = (
                "Не нашёл PDF-файл в этом диалоге. "
                "Загрузите PDF-файл и попросите сжать."
            )
            assistant_msg = Message(
                thread_id=thread.id,
                role=MessageRole.ASSISTANT,
                content=answer_text,
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
            return

        original_bytes = load_upload_bytes(pdf_file.storage_key)
        if not original_bytes:
            yield sse_event(
                "error",
                {"code": "compress_failed", "message": "Не удалось прочитать PDF-файл."},
            )
            return

        # Сжимаем
        status_text = f"Сжимаем PDF ({_LEVEL_LABELS.get(level, level)})…"
        for chunk in _chunks(status_text, 30):
            yield sse_event("token", {"text": chunk})

        try:
            compressed_bytes = compress_pdf_bytes(original_bytes, level)
        except Exception as exc:
            logger.warning("pdf compress failed: %s", exc)
            yield sse_event(
                "error",
                {"code": "compress_failed", "message": "Не удалось сжать PDF. Попробуйте позже."},
            )
            return

        orig_size = len(original_bytes)
        comp_size = len(compressed_bytes)
        reduction = int((1 - comp_size / max(orig_size, 1)) * 100)

        # Сохраняем сжатый файл
        new_file_id = uuid.uuid4()
        original_name = pdf_file.filename or "document.pdf"
        stem = original_name.rsplit(".", 1)[0] if "." in original_name else original_name
        compressed_name = f"{stem}_compressed.pdf"

        storage_key = save_upload_bytes(user.id, new_file_id, compressed_bytes, "pdf")
        now = datetime.now(timezone.utc)
        compressed_file = UploadedFile(
            id=new_file_id,
            user_id=user.id,
            filename=compressed_name,
            mime_type="application/pdf",
            size_bytes=comp_size,
            media_kind="compressed",
            storage_key=storage_key,
            extracted_text="",
            expires_at=now + timedelta(hours=_COMPRESSED_TTL_HOURS),
        )
        db.add(compressed_file)
        await db.flush()

        download_url = f"{(settings.public_web_url or 'https://glosix.ru').rstrip('/')}/api/files/{new_file_id}/content"

        result_text = (
            f"\n\n✅ Готово!\n"
            f"Исходный размер: {format_size(orig_size)}\n"
            f"После сжатия: {format_size(comp_size)}\n"
            f"Уменьшение: {reduction}%"
        )
        for chunk in _chunks(result_text, 40):
            yield sse_event("token", {"text": chunk})

        answer_full = status_text + result_text
        assistant_msg = Message(
            thread_id=thread.id,
            role=MessageRole.ASSISTANT,
            content=answer_full,
        )
        db.add(assistant_msg)
        thread.message_count = (thread.message_count or 0) + 2
        thread.last_message_at = datetime.now(timezone.utc)
        await db.commit()

        yield sse_event(
            "document_ready",
            {
                "file_id": str(new_file_id),
                "filename": compressed_name,
                "download_url": download_url,
                "ttl_hours": _COMPRESSED_TTL_HOURS,
            },
        )
        yield sse_event(
            "done",
            {
                "message_id": str(assistant_msg.id),
                "needs_search": False,
                "answer_model": "lite",
            },
        )

    await clear_search_pending(redis_client, thread.id)


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]
