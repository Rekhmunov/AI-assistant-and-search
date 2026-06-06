"""Юридические документы: версии, публичные URL, согласия при регистрации."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_user import AdminUser
from app.models.legal_document import LegalDocument, LegalDocumentVersion, UserLegalConsent
from app.models.user import User
from app.services.legal_html import sanitize_legal_html

DEFAULT_DOCUMENTS: tuple[tuple[str, str, str], ...] = (
    ("privacy", "Политика конфиденциальности", "/privacy"),
    ("pd_consent", "Согласие на обработку персональных данных", "/consent-personal-data"),
    ("cookies", "Политика использования cookie", "/cookies"),
)

REQUIRED_REGISTER_SLUGS = frozenset({"privacy", "pd_consent"})


def normalize_public_path(path: str) -> str:
    p = (path or "").strip()
    if not p.startswith("/"):
        p = f"/{p}"
    p = re.sub(r"/+", "/", p)
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


@dataclass(frozen=True)
class LegalDocumentPublic:
    slug: str
    title: str
    public_path: str
    version_id: uuid.UUID
    version_number: int
    content_html: str
    updated_at: str | None


async def ensure_default_documents(db: AsyncSession) -> None:
    for slug, title, public_path in DEFAULT_DOCUMENTS:
        result = await db.execute(select(LegalDocument).where(LegalDocument.slug == slug))
        doc = result.scalar_one_or_none()
        if doc:
            continue
        doc = LegalDocument(slug=slug, title=title, public_path=public_path)
        db.add(doc)
        await db.flush()
        version = LegalDocumentVersion(
            document_id=doc.id,
            version_number=1,
            content_html="<p></p>",
        )
        db.add(version)
        await db.flush()
        doc.current_version_id = version.id
    await db.flush()


async def list_documents_admin(db: AsyncSession) -> list[LegalDocument]:
    result = await db.execute(select(LegalDocument).order_by(LegalDocument.slug))
    return list(result.scalars().all())


async def get_document_by_slug(db: AsyncSession, slug: str) -> LegalDocument | None:
    result = await db.execute(select(LegalDocument).where(LegalDocument.slug == slug))
    return result.scalar_one_or_none()


async def get_document_by_path(db: AsyncSession, public_path: str) -> LegalDocument | None:
    path = normalize_public_path(public_path)
    result = await db.execute(select(LegalDocument).where(LegalDocument.public_path == path))
    return result.scalar_one_or_none()


async def list_versions(db: AsyncSession, document_id: uuid.UUID) -> list[LegalDocumentVersion]:
    result = await db.execute(
        select(LegalDocumentVersion)
        .where(LegalDocumentVersion.document_id == document_id)
        .order_by(LegalDocumentVersion.version_number.desc())
    )
    return list(result.scalars().all())


async def save_document_version(
    db: AsyncSession,
    *,
    slug: str,
    content_html: str,
    public_path: str | None,
    admin: AdminUser,
) -> LegalDocumentVersion:
    doc = await get_document_by_slug(db, slug)
    if not doc:
        raise ValueError(f"Unknown document slug: {slug}")

    if public_path is not None:
        new_path = normalize_public_path(public_path)
        if new_path != doc.public_path:
            clash = await db.execute(
                select(LegalDocument).where(
                    LegalDocument.public_path == new_path,
                    LegalDocument.id != doc.id,
                )
            )
            if clash.scalar_one_or_none():
                raise ValueError("Публичный URL уже используется другим документом")
            doc.public_path = new_path

    result = await db.execute(
        select(func.coalesce(func.max(LegalDocumentVersion.version_number), 0)).where(
            LegalDocumentVersion.document_id == doc.id
        )
    )
    max_ver = int(result.scalar_one() or 0)
    version = LegalDocumentVersion(
        document_id=doc.id,
        version_number=max_ver + 1,
        content_html=sanitize_legal_html(content_html),
        created_by_admin_id=admin.id,
        admin_email=admin.email,
    )
    db.add(version)
    await db.flush()
    doc.current_version_id = version.id
    await db.flush()
    return version


def document_to_public(doc: LegalDocument) -> LegalDocumentPublic | None:
    ver = doc.current_version
    if not ver:
        return None
    return LegalDocumentPublic(
        slug=doc.slug,
        title=doc.title,
        public_path=doc.public_path,
        version_id=ver.id,
        version_number=ver.version_number,
        content_html=ver.content_html,
        updated_at=doc.updated_at.isoformat() if doc.updated_at else None,
    )


async def record_user_consents(
    db: AsyncSession,
    user: User,
    *,
    privacy_version_id: uuid.UUID,
    pd_consent_version_id: uuid.UUID,
) -> None:
    mapping = {
        "privacy": privacy_version_id,
        "pd_consent": pd_consent_version_id,
    }
    for slug, version_id in mapping.items():
        doc = await get_document_by_slug(db, slug)
        if not doc or not doc.current_version_id:
            raise ValueError(f"Document not configured: {slug}")
        if doc.current_version_id != version_id:
            raise ValueError(f"Устаревшая версия документа: {slug}")
        ver_result = await db.execute(
            select(LegalDocumentVersion).where(
                LegalDocumentVersion.id == version_id,
                LegalDocumentVersion.document_id == doc.id,
            )
        )
        if not ver_result.scalar_one_or_none():
            raise ValueError(f"Invalid version for {slug}")
        db.add(
            UserLegalConsent(
                user_id=user.id,
                document_id=doc.id,
                version_id=version_id,
            )
        )
