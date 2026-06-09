"""Дедупликация повторных экспортов docx/pdf/md по хешу контента."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.uploaded_file import UploadedFile
from app.services.file_share_token import create_file_share_token, share_token_ttl_seconds_for_expires_at
from app.services.image_gen_service import public_file_content_url


def export_content_hash(*, fmt: str, content: str, title_hint: str | None) -> str:
    normalized = (content or "").strip()
    title = (title_hint or "").strip()
    payload = f"{fmt}\n{title}\n{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def find_reusable_export(
    db: AsyncSession,
    user_id: UUID,
    content_hash: str,
) -> UploadedFile | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UploadedFile)
        .where(
            UploadedFile.user_id == user_id,
            UploadedFile.media_kind == "generated_doc",
            UploadedFile.export_content_hash == content_hash,
            UploadedFile.expires_at.isnot(None),
            UploadedFile.expires_at > now,
        )
        .order_by(UploadedFile.expires_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def export_result_from_row(
    row: UploadedFile,
    *,
    settings: Settings | None = None,
) -> tuple[UUID, str, str, str, int]:
    settings = settings or get_settings()
    file_id = row.id
    filename = row.filename
    download_url = public_file_content_url(file_id, settings)
    ttl_seconds = share_token_ttl_seconds_for_expires_at(row.expires_at)
    share_token, _ = create_file_share_token(file_id, ttl_seconds=ttl_seconds, settings=settings)
    share_path = f"/api/files/{file_id}/shared?token={share_token}"
    ttl_hours = max(1, (ttl_seconds + 3599) // 3600)
    return file_id, filename, download_url, share_path, ttl_hours
