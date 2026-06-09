"""Сохранение сгенерированных файлов (docx, pdf)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.image_gen_service import public_file_content_url
from app.services.upload_storage import save_upload_bytes

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"
_MD_MIME = "text/markdown; charset=utf-8"


def _safe_filename(title: str, file_id: UUID, ext: str) -> str:
    base = re.sub(r"[^\w\s\-а-яА-ЯёЁ]+", "", title, flags=re.UNICODE).strip()
    base = re.sub(r"\s+", "-", base)[:80] or "document"
    return f"{base}-{file_id.hex[:8]}.{ext}"


async def persist_generated_file(
    db: AsyncSession,
    user: User,
    file_bytes: bytes,
    *,
    title: str,
    ttl_hours: int,
    ext: str,
    mime_type: str,
    export_content_hash: str | None = None,
) -> tuple[UUID, str, str]:
    file_id = uuid4()
    now = datetime.now(timezone.utc)
    storage_key = save_upload_bytes(user.id, file_id, file_bytes, ext)
    filename = _safe_filename(title, file_id, ext)
    row = UploadedFile(
        id=file_id,
        user_id=user.id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(file_bytes),
        media_kind="generated_doc",
        storage_key=storage_key,
        extracted_text="",
        export_content_hash=export_content_hash,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    db.add(row)
    await db.flush()
    url = public_file_content_url(file_id)
    return file_id, filename, url


async def persist_generated_docx(
    db: AsyncSession,
    user: User,
    docx_bytes: bytes,
    *,
    title: str,
    ttl_hours: int,
    export_content_hash: str | None = None,
) -> tuple[UUID, str, str]:
    return await persist_generated_file(
        db,
        user,
        docx_bytes,
        title=title,
        ttl_hours=ttl_hours,
        ext="docx",
        mime_type=_DOCX_MIME,
        export_content_hash=export_content_hash,
    )


async def persist_generated_pdf(
    db: AsyncSession,
    user: User,
    pdf_bytes: bytes,
    *,
    title: str,
    ttl_hours: int,
    export_content_hash: str | None = None,
) -> tuple[UUID, str, str]:
    return await persist_generated_file(
        db,
        user,
        pdf_bytes,
        title=title,
        ttl_hours=ttl_hours,
        ext="pdf",
        mime_type=_PDF_MIME,
        export_content_hash=export_content_hash,
    )


async def persist_generated_markdown(
    db: AsyncSession,
    user: User,
    markdown_bytes: bytes,
    *,
    title: str,
    ttl_hours: int,
    export_content_hash: str | None = None,
) -> tuple[UUID, str, str]:
    return await persist_generated_file(
        db,
        user,
        markdown_bytes,
        title=title,
        ttl_hours=ttl_hours,
        ext="md",
        mime_type=_MD_MIME,
        export_content_hash=export_content_hash,
    )
