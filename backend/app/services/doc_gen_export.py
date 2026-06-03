"""Экорт текста из чата (блок ```txt) в Word без нового поискового запроса."""

from __future__ import annotations

import re
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.limiter import RateLimiter
from app.models.user import Plan, User
from app.services.app_settings import get_setting
from app.services.doc_gen_llm import generate_document_structure
from app.services.doc_gen_plain import structure_from_plain_text
from app.services.doc_gen_schema import DocumentStructure, DocumentStructureError
from app.services.doc_gen_storage import persist_generated_docx
from app.services.docx_builder import build_docx_bytes
from app.services.file_share_token import create_file_share_token
from app.services.providers.factory import resolve_runtime_providers

MAX_EXPORT_CHARS = 50_000


def _guess_title(content: str, title_hint: str | None) -> str:
    if title_hint and title_hint.strip():
        return title_hint.strip()[:200]
    for line in content.splitlines():
        s = line.strip()
        if len(s) >= 8 and len(s) <= 200:
            return s[:200]
    return "Документ"


def _safe_docx_filename(title: str, file_id: UUID) -> str:
    base = re.sub(r"[^\w\s\-а-яА-ЯёЁ]+", "", title, flags=re.UNICODE).strip()
    base = re.sub(r"\s+", "-", base)[:80] or "document"
    return f"{base}-{file_id.hex[:8]}.docx"


async def export_chat_text_to_docx(
    db: AsyncSession,
    redis_client: redis.Redis,
    user: User,
    limiter: RateLimiter,
    *,
    content: str,
    title_hint: str | None = None,
) -> tuple[UUID, str, str, str, int]:
    """
    Возвращает (file_id, filename, download_url, share_path, ttl_hours).
    """
    settings = get_settings()
    user_id_str = str(user.id)
    text = (content or "").strip()
    if len(text) < 40:
        raise DocumentStructureError("content_too_short")
    if len(text) > MAX_EXPORT_CHARS:
        text = text[:MAX_EXPORT_CHARS]

    allowed, _, _ = await limiter.check_doc_gen_allowed(user_id_str, user)
    if not allowed:
        raise DocumentStructureError("doc_gen_rate_limit")

    ttl_hours = int(
        await get_setting("generated_doc_ttl_hours", db, redis_client, settings)
    )
    ttl_hours = max(1, min(ttl_hours, 24 * 30))

    llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    answer_model = "pro" if user.plan == Plan.PRO else "lite"

    doc_prompt = (
        "Запрос пользователя: оформи приведённый текст как Word-документ для скачивания.\n\n"
        "Исходный материал из блока ответа (перенеси в документ полностью, по разделам):\n"
        f"---\n{text}\n---"
    )

    structure: DocumentStructure | None = structure_from_plain_text(text)
    if structure is None:
        structure = await generate_document_structure(
            llm,
            doc_prompt,
            answer_model=answer_model,
        )
    docx_bytes = build_docx_bytes(structure, show_glosix_footer=user.plan != Plan.PRO)
    if len(docx_bytes) < 256:
        raise DocumentStructureError("empty_docx")

    title = _guess_title(text, title_hint or structure.title)
    file_id, _, download_url = await persist_generated_docx(
        db,
        user,
        docx_bytes,
        title=title,
        ttl_hours=ttl_hours,
    )
    filename = _safe_docx_filename(title, file_id)
    share_token, _ = create_file_share_token(
        file_id,
        ttl_seconds=ttl_hours * 3600,
        settings=settings,
    )
    share_path = f"/api/files/{file_id}/shared?token={share_token}"

    await limiter.record_doc_gen_success(user_id_str, user)
    await db.commit()

    return file_id, filename, download_url, share_path, ttl_hours
