from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
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
    settings = get_settings()
    max_bytes = 20 * 1024 * 1024 if user.plan == Plan.PRO else 10 * 1024 * 1024

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
            detail=f"Файл слишком большой (макс. {max_bytes // 1024 // 1024} МБ)",
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
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(row)
    await db.flush()

    excerpt = text[:500] + ("…" if len(text) > 500 else "")
    return UploadedFileOut(id=row.id, filename=filename, size_bytes=len(data), excerpt=excerpt)
