from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.constants.attachments import (
    UPLOAD_TTL_HOURS,
    max_upload_bytes,
    max_upload_mb,
)
from app.models.uploaded_file import UploadedFile
from app.models.user import Plan, User
from app.services.file_parser import DOCUMENT_EXT, IMAGE_EXT, extract_text

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXT = DOCUMENT_EXT | IMAGE_EXT

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/csv": "csv",
}


def _resolve_extension(filename: str, content_type: str | None) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ALLOWED_EXT:
        return ext
    if content_type:
        mapped = _MIME_TO_EXT.get(content_type.split(";")[0].strip().lower())
        if mapped:
            return mapped
    return ext


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


class UploadedFileOut(BaseModel):
    id: UUID
    filename: str
    size_bytes: int
    excerpt: str


@router.post("/upload", response_model=UploadedFileOut)
async def upload_file(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
):
    max_bytes = max_upload_bytes(user.plan)
    now = datetime.now(timezone.utc)

    await db.execute(
        delete(UploadedFile).where(
            UploadedFile.user_id == user.id,
            UploadedFile.expires_at.isnot(None),
            UploadedFile.expires_at < now,
        )
    )

    filename = file.filename or "file"
    ext = _resolve_extension(filename, file.content_type)
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Формат не поддерживается. Допустимо: PDF, Word, Excel, CSV, текст, JPEG, PNG, WebP.",
        )
    if ext in IMAGE_EXT and "." not in filename:
        filename = f"{filename}.{ext}"

    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_file_too_large_detail(filename, len(data), user),
        )

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
        user_id=user.id,
        filename=filename,
        mime_type=file.content_type,
        size_bytes=len(data),
        extracted_text=text,
        expires_at=now + timedelta(hours=UPLOAD_TTL_HOURS),
    )
    db.add(row)
    await db.flush()

    excerpt = text[:500] + ("…" if len(text) > 500 else "")
    return UploadedFileOut(id=row.id, filename=filename, size_bytes=len(data), excerpt=excerpt)
