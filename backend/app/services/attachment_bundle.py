"""Сборка вложений: текст (OCR/документы) и фото для vision."""

from __future__ import annotations

import base64
import io
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

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
    uploaded_files: list[UploadedFile] = field(default_factory=list)


def convert_image_to_jpeg(data: bytes) -> bytes:
    """Конвертирует изображение в JPEG (для провайдеров не поддерживающих WebP/HEIC)."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except Exception:
        return data


def normalize_for_gigachat(vi: "VisionImage") -> "VisionImage":
    """Конвертирует изображение в JPEG если GigaChat не поддерживает формат (WebP, HEIC и т.д.)."""
    supported = ("image/jpeg", "image/png")
    if vi.media_type in supported:
        return vi
    raw = base64.standard_b64decode(vi.data_base64)
    jpeg_data = convert_image_to_jpeg(raw)
    logger.debug(
        "VISION_DEBUG normalized %s → image/jpeg for GigaChat (len %d→%d)",
        vi.media_type, len(raw), len(jpeg_data),
    )
    return VisionImage(
        filename=vi.filename.rsplit(".", 1)[0] + ".jpg",
        media_type="image/jpeg",
        data_base64=base64.standard_b64encode(jpeg_data).decode("ascii"),
    )


def _pdf_pages_to_vision_images(
    filename: str,
    pdf_bytes: bytes | None,
    *,
    max_pages: int = 3,
    dpi: int = 150,
) -> list[VisionImage]:
    """
    Конвертирует первые max_pages страниц PDF в JPEG-изображения для Vision.
    Используется когда pypdf не смог извлечь текст (скан/изображение в PDF).
    """
    if not pdf_bytes:
        return []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        result: list[VisionImage] = []
        for page_num in range(min(max_pages, len(doc))):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
            jpg_bytes = pix.tobytes(output="jpeg", jpg_quality=85)
            img_b64 = base64.standard_b64encode(jpg_bytes).decode("ascii")
            page_name = f"{filename}_page{page_num + 1}.jpg"
            result.append(VisionImage(
                filename=page_name,
                media_type="image/jpeg",
                data_base64=img_b64,
            ))
        return result
    except Exception as exc:
        logger.warning("_pdf_pages_to_vision_images failed for %s: %s", filename, exc)
        return []


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
            effective_mime = f.mime_type or mime_for_ext(ext)
            logger.debug(
                "VISION_DEBUG bundle file=%s db_mime=%s effective_mime=%s",
                f.filename, f.mime_type, effective_mime,
            )
            vision_images.append(
                VisionImage(
                    filename=f.filename,
                    media_type=effective_mime,
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
            # Текст не извлечён — возможно скан-PDF.
            # Конвертируем первые 3 страницы в изображения и прогоняем через Vision.
            raw = load_upload_bytes(f.storage_key)
            _pdf_images = _pdf_pages_to_vision_images(f.filename, raw, max_pages=3)
            if _pdf_images:
                vision_images.extend(_pdf_images)
                logger.info(
                    "attachment_bundle: scanned PDF %s → %d vision images",
                    f.filename, len(_pdf_images),
                )
            else:
                raise ValueError("attachment_empty")

    llm_query = "\n".join(parts)
    # В UI имена файлов показываются чипами вложений; в текст вопроса маркер не дублируем.
    display = query
    return AttachmentBundle(
        llm_query=llm_query,
        display_query=display,
        vision_images=vision_images,
        needs_vision=bool(vision_images),
        has_document_text=has_document_text,
        uploaded_files=files,
    )
