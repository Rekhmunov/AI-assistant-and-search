"""Сохранение сгенерированного .docx."""

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


def _safe_filename(title: str, file_id: UUID) -> str:
    base = re.sub(r"[^\w\s\-а-яА-ЯёЁ]+", "", title, flags=re.UNICODE).strip()
    base = re.sub(r"\s+", "-", base)[:80] or "document"
    return f"{base}-{file_id.hex[:8]}.docx"


async def persist_generated_docx(
    db: AsyncSession,
    user: User,
    docx_bytes: bytes,
    *,
    title: str,
    ttl_hours: int,
) -> tuple[UUID, str, str]:
    file_id = uuid4()
    now = datetime.now(timezone.utc)
    storage_key = save_upload_bytes(user.id, file_id, docx_bytes, "docx")
    filename = _safe_filename(title, file_id)
    row = UploadedFile(
        id=file_id,
        user_id=user.id,
        filename=filename,
        mime_type=_DOCX_MIME,
        size_bytes=len(docx_bytes),
        media_kind="generated_doc",
        storage_key=storage_key,
        extracted_text="",
        expires_at=now + timedelta(hours=ttl_hours),
    )
    db.add(row)
    await db.flush()
    url = public_file_content_url(file_id)
    return file_id, filename, url
