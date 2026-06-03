from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_file_access_user
from app.constants.attachments import (
    UPLOAD_TTL_HOURS,
    max_upload_bytes,
    max_upload_mb,
)
from app.models.uploaded_file import UploadedFile
from app.models.user import Plan, User
from app.services.file_format import (
    ALLOWED_EXT,
    UNSUPPORTED_FORMAT_MESSAGE,
    normalize_filename,
    resolve_upload_extension,
)
from app.services.file_parser import DOCUMENT_EXT, IMAGE_EXT, extract_text, ocr_image_bytes, prepare_image_for_ocr
from app.services.file_share_token import verify_file_share_token
from app.services.http_disposition import attachment_content_disposition
from app.services.upload_storage import delete_upload_file, load_upload_bytes, mime_for_ext, save_upload_bytes

router = APIRouter(prefix="/files", tags=["files"])


def _file_too_large_detail(filename: str, size: int, user: User) -> dict[str, Any]:
    limit = max_upload_bytes(user.plan)
    limit_mb = max_upload_mb(user.plan)
    file_mb = round(size / (1024 * 1024), 1)
    pro_mb = max_upload_mb(Plan.PRO)
    if user.plan == Plan.FREE:
        message = (
            f"«{filename}» ({file_mb} МБ) превышает лимит Free ({limit_mb} МБ). "
            f"Перейдите на Pro — до {pro_mb} МБ на файл."
        )
        suggest_pro = True
    else:
        message = f"«{filename}» ({file_mb} МБ) превышает лимит ({limit_mb} МБ)."
        suggest_pro = False
    return {
        "code": "file_too_large",
        "message": message,
        "suggest_pro": suggest_pro,
        "max_bytes": limit,
        "size_bytes": size,
    }


class UploadedFileMetaOut(BaseModel):
    id: UUID
    filename: str
    media_kind: str
    preview_url: str | None = None


@router.get("/{file_id}/meta", response_model=UploadedFileMetaOut)
async def file_meta(
    file_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_file_access_user)],
):
    """Метаданные загруженного файла для превью в чате."""
    from app.services.image_gen_service import public_file_content_url

    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == file_id,
            UploadedFile.user_id == user.id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row.expires_at and row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="File expired")
    preview = None
    if row.media_kind in ("image", "generated", "generated_doc") and row.storage_key:
        preview = public_file_content_url(file_id)
    return UploadedFileMetaOut(
        id=row.id,
        filename=row.filename,
        media_kind=row.media_kind or "document",
        preview_url=preview,
    )


@router.get("/{file_id}/content")
async def download_file_content(
    file_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_file_access_user)],
):
    """Скачивание сгенерированных и загруженных файлов (JWT, refresh или guest cookie)."""
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == file_id,
            UploadedFile.user_id == user.id,
        )
    )
    row = result.scalar_one_or_none()
    if not row or not row.storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row.expires_at and row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="File expired")
    if row.media_kind not in ("image", "generated", "generated_doc"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    data = load_upload_bytes(row.storage_key)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    mime = row.mime_type or mime_for_ext(row.storage_key.rsplit(".", 1)[-1])
    disposition = (
        attachment_content_disposition(row.filename)
        if row.media_kind == "generated_doc"
        else "attachment"
    )
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": disposition,
        },
    )


@router.get("/{file_id}/shared")
async def download_file_shared(
    file_id: UUID,
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Скачивание по подписанной ссылке (share fallback без Bearer)."""
    if not verify_file_share_token(file_id, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired link")
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    row = result.scalar_one_or_none()
    if not row or not row.storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row.expires_at and row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="File expired")
    if row.media_kind not in ("generated_doc", "generated", "image"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    data = load_upload_bytes(row.storage_key)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    mime = row.mime_type or mime_for_ext(row.storage_key.rsplit(".", 1)[-1])
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": attachment_content_disposition(row.filename),
        },
    )


class UploadedFileOut(BaseModel):
    id: UUID
    filename: str
    size_bytes: int
    excerpt: str
    media_kind: str
    has_text: bool


@router.post("/upload", response_model=UploadedFileOut)
async def upload_file(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
):
    max_bytes = max_upload_bytes(user.plan)
    now = datetime.now(timezone.utc)

    expired_rows = await db.execute(
        select(UploadedFile).where(
            UploadedFile.user_id == user.id,
            UploadedFile.expires_at.isnot(None),
            UploadedFile.expires_at < now,
        )
    )
    for old in expired_rows.scalars().all():
        delete_upload_file(old.storage_key)
    await db.execute(
        delete(UploadedFile).where(
            UploadedFile.user_id == user.id,
            UploadedFile.expires_at.isnot(None),
            UploadedFile.expires_at < now,
        )
    )

    filename = file.filename or "upload"
    data = await file.read()

    ext = resolve_upload_extension(filename, file.content_type, data)
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=UNSUPPORTED_FORMAT_MESSAGE,
        )

    filename = normalize_filename(filename, ext)

    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_file_too_large_detail(filename, len(data), user),
        )

    file_id = uuid4()

    if ext in IMAGE_EXT:
        try:
            ocr_data, ocr_ext = prepare_image_for_ocr(data, ext)
            if ocr_ext != ext:
                filename = normalize_filename(filename, ocr_ext)
                ext = ocr_ext
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

        storage_key = save_upload_bytes(user.id, file_id, ocr_data, ext)
        ocr_text = ocr_image_bytes(ocr_data)

        row = UploadedFile(
            id=file_id,
            user_id=user.id,
            filename=filename,
            mime_type=file.content_type or mime_for_ext(ext),
            size_bytes=len(data),
            media_kind="image",
            storage_key=storage_key,
            extracted_text=ocr_text,
            expires_at=now + timedelta(hours=UPLOAD_TTL_HOURS),
        )
        db.add(row)
        await db.flush()

        if ocr_text:
            excerpt = ocr_text[:500] + ("…" if len(ocr_text) > 500 else "")
        else:
            excerpt = "Фото загружено — ответ по изображению"
        return UploadedFileOut(
            id=row.id,
            filename=filename,
            size_bytes=len(data),
            excerpt=excerpt,
            media_kind="image",
            has_text=bool(ocr_text.strip()),
        )

    # Документы: только текст, без бинарника на диске
    try:
        text = extract_text(filename, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Не удалось прочитать файл",
        ) from None

    if not text.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Файл пустой или без текста")

    row = UploadedFile(
        id=file_id,
        user_id=user.id,
        filename=filename,
        mime_type=file.content_type,
        size_bytes=len(data),
        media_kind="document",
        storage_key=None,
        extracted_text=text,
        expires_at=now + timedelta(hours=UPLOAD_TTL_HOURS),
    )
    db.add(row)
    await db.flush()

    excerpt = text[:500] + ("…" if len(text) > 500 else "")
    return UploadedFileOut(
        id=row.id,
        filename=filename,
        size_bytes=len(data),
        excerpt=excerpt,
        media_kind="document",
        has_text=True,
    )
