"""Сборка вложений: текст (OCR/документы) и фото для vision."""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.attachments import (
    MAX_ATTACHMENTS_PER_SEARCH,
    MAX_EXTRACT_CHARS_PER_FILE,
    MAX_TOTAL_ATTACHMENT_CHARS,
)
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.file_parser import IMAGE_EXT
from app.services.upload_storage import load_upload_bytes, mime_for_ext


# Меньше — считаем, что OCR не дал полезного текста, нужен vision.
MIN_OCR_CHARS_FOR_TEXT_ONLY = 48


@dataclass
class VisionImage:
    filename: str
    media_type: str
    data_base64: str


@dataclass
class AttachmentBundle:
    llm_query: str
    display_query: str
    vision_images: list[VisionImage] = field(default_factory=list)
    needs_vision: bool = False
    has_document_text: bool = False


def _is_image_row(row: UploadedFile) -> bool:
    if (row.media_kind or "").lower() == "image":
        return True
    ext = row.filename.rsplit(".", 1)[-1].lower() if "." in row.filename else ""
    return ext in IMAGE_EXT


async def resolve_attachment_bundle(
    db: AsyncSession,
    user: User,
    query: str,
    attachment_ids: list[uuid.UUID] | None,
) -> AttachmentBundle:
    if not attachment_ids:
        return AttachmentBundle(llm_query=query, display_query=query)

    if len(attachment_ids) > MAX_ATTACHMENTS_PER_SEARCH:
        raise ValueError("attachment_limit")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id.in_(attachment_ids),
            UploadedFile.user_id == user.id,
            UploadedFile.expires_at.isnot(None),
            UploadedFile.expires_at > now,
        )
    )
    by_id = {f.id: f for f in result.scalars().all()}
    if len(by_id) != len(attachment_ids):
        raise ValueError("attachment_expired")

    files = [by_id[fid] for fid in attachment_ids]
    names = [f.filename for f in files]
    parts = [query]
    vision_images: list[VisionImage] = []
    budget = MAX_TOTAL_ATTACHMENT_CHARS
    has_document_text = False

    for f in files:
        chunk = (f.extracted_text or "").strip()
        is_image = _is_image_row(f)

        if is_image and len(chunk) < MIN_OCR_CHARS_FOR_TEXT_ONLY:
            raw = load_upload_bytes(f.storage_key)
            if not raw:
                raise ValueError("attachment_storage_missing")
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "jpg"
            vision_images.append(
                VisionImage(
                    filename=f.filename,
                    media_type=f.mime_type or mime_for_ext(ext),
                    data_base64=base64.standard_b64encode(raw).decode("ascii"),
                )
            )
            if chunk:
                parts.append(f"\n\n--- Текст с фото (OCR): {f.filename} ---\n{chunk}")
                has_document_text = True
            continue

        if chunk:
            if len(chunk) > MAX_EXTRACT_CHARS_PER_FILE:
                chunk = chunk[:MAX_EXTRACT_CHARS_PER_FILE] + "\n… [обрезано]"
            if len(chunk) > budget:
                chunk = chunk[: max(0, budget)] + ("\n… [обрезано]" if budget > 0 else "")
            budget -= len(chunk)
            label = "Фото" if is_image else "Документ"
            parts.append(f"\n\n--- {label}: {f.filename} ---\n{chunk}")
            has_document_text = True
            if budget <= 0:
                break
        elif not is_image:
            raise ValueError("attachment_empty")

    llm_query = "\n".join(parts)
    display = f"{query}\n\n[Файлы: {', '.join(names)}]" if names else query
    return AttachmentBundle(
        llm_query=llm_query,
        display_query=display,
        vision_images=vision_images,
        needs_vision=bool(vision_images),
        has_document_text=has_document_text,
    )
