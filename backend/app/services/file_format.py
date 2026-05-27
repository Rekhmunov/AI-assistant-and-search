"""Detect upload format from filename, MIME, and file signature."""

from __future__ import annotations

from app.services.file_parser import DOCUMENT_EXT, IMAGE_EXT

ALLOWED_EXT = DOCUMENT_EXT | IMAGE_EXT | frozenset({"heic", "heif"})

_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
}


def sniff_ext_from_bytes(data: bytes) -> str | None:
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heif"):
            return "heic"
    if len(data) >= 4 and data[:4] == b"%PDF":
        return "pdf"
    return None


def resolve_upload_extension(
    filename: str,
    content_type: str | None,
    data: bytes,
) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "jpeg":
        ext = "jpg"
    if ext in ALLOWED_EXT:
        return ext

    if content_type:
        mime = content_type.split(";")[0].strip().lower()
        mapped = _MIME_TO_EXT.get(mime)
        if mapped:
            return mapped

    sniffed = sniff_ext_from_bytes(data)
    if sniffed:
        return sniffed

    return ext


def normalize_filename(filename: str, ext: str) -> str:
    base = filename.rsplit(".", 1)[0] if "." in filename else filename
    if not base or base == "blob":
        base = "upload"
    return f"{base}.{ext}"


UNSUPPORTED_FORMAT_MESSAGE = (
    "Формат не поддерживается. Допустимо: PDF, Word, Excel, CSV, текст, "
    "фото JPEG, PNG, WebP, HEIC."
)
