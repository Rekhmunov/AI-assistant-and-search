from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    GUEST_HEADER,
    SearchUserResult,
    get_db,
    get_file_access_user,
    get_rate_limiter,
    get_redis,
    get_search_user,
    set_guest_cookie,
)
from app.core.limiter import RateLimiter
from app.constants.attachments import MAX_UPLOAD_BYTES_FREE, MAX_UPLOAD_BYTES_PRO
from app.services.upload_lifecycle import resolve_max_upload_mb_free, resolve_max_upload_mb_pro
from app.models.uploaded_file import UploadedFile
from app.models.user import Plan, User
from app.services.file_format import (
    ALLOWED_EXT,
    UNSUPPORTED_FORMAT_MESSAGE,
    normalize_filename,
    resolve_upload_extension,
)
from app.services.file_parser import DOCUMENT_EXT, IMAGE_EXT, extract_text, ocr_image_bytes, prepare_image_for_ocr
from app.services.doc_gen_export import (
    export_chat_text_to_docx,
    export_chat_text_to_markdown,
    export_chat_text_to_pdf,
)
from app.services.doc_gen_schema import DocumentStructureError
from app.services.file_share_token import verify_file_share_token
from app.services.http_disposition import attachment_content_disposition
from app.services.upload_lifecycle import (
    cleanup_expired_uploads,
    purge_expired_file_if_needed,
    resolve_upload_ttl_hours,
)
from app.services.upload_storage import load_upload_bytes, mime_for_ext, save_upload_bytes

router = APIRouter(prefix="/files", tags=["files"])


def _file_too_large_detail(filename: str, size: int, user: User, *, limit_mb_free: int, limit_mb_pro: int) -> dict[str, Any]:
    file_mb = round(size / (1024 * 1024), 1)
    if user.plan == Plan.PRO:
        limit_mb = limit_mb_pro
        limit_bytes = limit_mb * 1024 * 1024
        message = f"«{filename}» ({file_mb} МБ) превышает лимит ({limit_mb} МБ)."
        suggest_pro = False
    else:
        limit_mb = limit_mb_free
        limit_bytes = limit_mb * 1024 * 1024
        message = (
            f"«{filename}» ({file_mb} МБ) превышает лимит Free ({limit_mb} МБ). "
            f"Перейдите на Pro — до {limit_mb_pro} МБ на файл."
        )
        suggest_pro = True
    return {
        "code": "file_too_large",
        "message": message,
        "suggest_pro": suggest_pro,
        "max_bytes": limit_bytes,
        "size_bytes": size,
    }


class UploadedFileMetaOut(BaseModel):
    id: UUID
    filename: str
    media_kind: str
    preview_url: str | None = None
    expires_at: datetime | None = None


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
    if await purge_expired_file_if_needed(db, row):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="File expired")
    preview = None
    if row.media_kind in ("image", "generated", "generated_doc") and row.storage_key:
        preview = public_file_content_url(file_id)
    return UploadedFileMetaOut(
        id=row.id,
        filename=row.filename,
        media_kind=row.media_kind or "document",
        preview_url=preview,
        expires_at=row.expires_at,
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
    if await purge_expired_file_if_needed(db, row):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="File expired")
    if row.media_kind not in ("image", "generated", "generated_doc", "compressed", "converted"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    data = load_upload_bytes(row.storage_key)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    mime = row.mime_type or mime_for_ext(row.storage_key.rsplit(".", 1)[-1])
    disposition = (
        attachment_content_disposition(row.filename)
        if row.media_kind in ("generated_doc", "compressed", "converted")
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
    if await purge_expired_file_if_needed(db, row):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="File expired")
    if row.media_kind not in ("generated_doc", "generated", "image", "compressed", "converted"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    data = load_upload_bytes(row.storage_key)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    mime = row.mime_type or mime_for_ext(row.storage_key.rsplit(".", 1)[-1])
    return Response(
        content=data,
        media_type=mime,
        headers={
            "X-Robots-Tag": "noindex, nofollow, noarchive",
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


class ExportDocxIn(BaseModel):
    content: str = Field(..., min_length=40, max_length=50_000)
    title: str | None = Field(None, max_length=200)


class ExportMarkdownIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=50_000)
    title: str | None = Field(None, max_length=200)


class ExportedDocxOut(BaseModel):
    id: UUID
    filename: str
    url: str | None = None
    share_url: str
    ttl_hours: int


class ExportedPdfOut(BaseModel):
    id: UUID
    filename: str
    url: str | None = None
    share_url: str
    ttl_hours: int


class ExportedMarkdownOut(BaseModel):
    id: UUID
    filename: str
    url: str | None = None
    share_url: str
    ttl_hours: int


def _export_block_error(exc: DocumentStructureError) -> HTTPException:
    code = str(exc)
    if code == "doc_gen_pro_only":
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Скачивание документов доступно только в версии Pro",
        )
    if code == "doc_gen_rate_limit":
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="На сегодня лимит генерации документов исчерпан",
        )
    if code == "content_too_short":
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Слишком мало текста для документа",
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Не удалось сформировать документ",
    )


@router.post("/export-docx", response_model=ExportedDocxOut)
async def export_docx_from_answer_block(
    body: ExportDocxIn,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[SearchUserResult, Depends(get_search_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    """Word из текста блока ответа (оферта в ```txt и т.п.), без нового SSE-поиска."""
    redis_client = await get_redis()
    if actor.new_guest_key:
        set_guest_cookie(response, actor.new_guest_key)

    try:
        file_id, filename, download_url, share_path, ttl_hours = await export_chat_text_to_docx(
            db,
            redis_client,
            actor.user,
            limiter,
            content=body.content,
            title_hint=body.title,
        )
    except DocumentStructureError as exc:
        raise _export_block_error(exc) from exc

    return ExportedDocxOut(
        id=file_id,
        filename=filename,
        url=download_url,
        share_url=share_path,
        ttl_hours=ttl_hours,
    )


@router.post("/export-pdf", response_model=ExportedPdfOut)
async def export_pdf_from_answer_block(
    body: ExportDocxIn,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[SearchUserResult, Depends(get_search_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    """PDF из markdown-блока ответа по запросу из меню «Скачать»."""
    redis_client = await get_redis()
    if actor.new_guest_key:
        set_guest_cookie(response, actor.new_guest_key)

    try:
        file_id, filename, download_url, share_path, ttl_hours = await export_chat_text_to_pdf(
            db,
            redis_client,
            actor.user,
            limiter,
            content=body.content,
            title_hint=body.title,
        )
    except DocumentStructureError as exc:
        raise _export_block_error(exc) from exc

    return ExportedPdfOut(
        id=file_id,
        filename=filename,
        url=download_url,
        share_url=share_path,
        ttl_hours=ttl_hours,
    )


@router.post("/export-markdown", response_model=ExportedMarkdownOut)
async def export_markdown_from_answer_block(
    body: ExportMarkdownIn,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[SearchUserResult, Depends(get_search_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    """Markdown из блока ответа — для скачивания в MAX WebApp (нужен https URL)."""
    redis_client = await get_redis()
    if actor.new_guest_key:
        set_guest_cookie(response, actor.new_guest_key)

    try:
        file_id, filename, download_url, share_path, ttl_hours = await export_chat_text_to_markdown(
            db,
            redis_client,
            actor.user,
            limiter,
            content=body.content,
            title_hint=body.title,
        )
    except DocumentStructureError as exc:
        raise _export_block_error(exc) from exc

    return ExportedMarkdownOut(
        id=file_id,
        filename=filename,
        url=download_url,
        share_url=share_path,
        ttl_hours=ttl_hours,
    )


@router.post("/upload", response_model=UploadedFileOut)
async def upload_file(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[SearchUserResult, Depends(get_search_user)],
    file: UploadFile = File(...),
):
    if actor.new_guest_key:
        set_guest_cookie(response, actor.new_guest_key)
        response.headers[GUEST_HEADER] = actor.new_guest_key

    user = actor.user
    now = datetime.now(timezone.utc)
    redis_client = await get_redis()
    upload_ttl_hours = await resolve_upload_ttl_hours(db, redis_client)
    limit_mb_free = await resolve_max_upload_mb_free(db, redis_client)
    limit_mb_pro = await resolve_max_upload_mb_pro(db, redis_client)
    max_bytes = (limit_mb_pro if user.plan == Plan.PRO else limit_mb_free) * 1024 * 1024

    await cleanup_expired_uploads(db, user_id=user.id)

    filename = file.filename or "upload"
    data = await file.read()

    # Если данные пустые — скорее всего nginx обрезал тело по client_max_body_size
    if not data:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Файл не получен — возможно превышен лимит размера на сервере. Обратитесь к администратору.",
        )

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
            detail=_file_too_large_detail(filename, len(data), user, limit_mb_free=limit_mb_free, limit_mb_pro=limit_mb_pro),
        )

    file_id = uuid4()

    if ext in IMAGE_EXT:
        ocr_data = data
        ocr_ext = ext
        try:
            ocr_data, ocr_ext = prepare_image_for_ocr(data, ext)
            if ocr_ext != ext:
                filename = normalize_filename(filename, ocr_ext)
                ext = ocr_ext
        except ValueError as e:
            if ext in ("heic", "heif"):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
            # MAX / WebView: иногда битые метаданные — пробуем открыть как JPEG/PNG по сигнатуре.
            from app.services.file_format import sniff_ext_from_bytes

            sniffed = sniff_ext_from_bytes(data)
            if sniffed in IMAGE_EXT:
                try:
                    ocr_data, ocr_ext = prepare_image_for_ocr(data, sniffed)
                    filename = normalize_filename(filename, ocr_ext)
                    ext = ocr_ext
                except ValueError:
                    ocr_data, ocr_ext = data, sniffed
                    filename = normalize_filename(filename, ocr_ext)
                    ext = ocr_ext
            else:
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
            expires_at=now + timedelta(hours=upload_ttl_hours),
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

    # Документы: извлекаем текст; PDF дополнительно сохраняем бинарник для сжатия
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

    # PDF сохраняем на диск чтобы позволить сжатие через Ghostscript
    doc_storage_key: str | None = None
    if ext == "pdf":
        doc_storage_key = save_upload_bytes(user.id, file_id, data, ext)

    row = UploadedFile(
        id=file_id,
        user_id=user.id,
        filename=filename,
        mime_type=file.content_type,
        size_bytes=len(data),
        media_kind="document",
        storage_key=doc_storage_key,
        extracted_text=text,
        expires_at=now + timedelta(hours=upload_ttl_hours),
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
