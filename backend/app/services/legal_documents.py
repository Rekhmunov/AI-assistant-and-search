"""Юридические документы: версии, публичные URL, согласия при регистрации."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

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
    ("offer", "Публичная оферта", "/offer"),
    ("terms", "Пользовательское соглашение", "/terms"),
)

REQUIRED_REGISTER_SLUGS = frozenset({"privacy", "pd_consent"})
RECONSENT_SLUGS = frozenset({"privacy", "pd_consent", "cookies"})

ONLY_VERSION_ERROR = "Нельзя удалить единственную версию документа"
CONSENT_BLOCKED_ERROR = "Нельзя удалить версию: с ней ознакомился хотя бы один пользователь"


class LegalVersionDeleteBlocked(Exception):
    """Версию нельзя удалить из‑за согласий пользователей."""


def normalize_public_path(path: str) -> str:
    p = (path or "").strip()
    if not p.startswith("/"):
        p = f"/{p}"
    p = re.sub(r"/+", "/", p)
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


@dataclass(frozen=True)
class ConsentMeta:
    source: str
    consent_method: str
    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True)
class PendingConsent:
    slug: str
    title: str
    public_path: str
    version_id: uuid.UUID
    version_number: int


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


async def consent_counts_for_versions(
    db: AsyncSession,
    version_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    if not version_ids:
        return {}
    result = await db.execute(
        select(UserLegalConsent.version_id, func.count())
        .where(UserLegalConsent.version_id.in_(version_ids))
        .group_by(UserLegalConsent.version_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


async def delete_document_version(
    db: AsyncSession,
    *,
    slug: str,
    version_id: uuid.UUID,
) -> LegalDocument:
    doc = await get_document_by_slug(db, slug)
    if not doc:
        raise ValueError("Document not found")

    ver_result = await db.execute(
        select(LegalDocumentVersion).where(
            LegalDocumentVersion.id == version_id,
            LegalDocumentVersion.document_id == doc.id,
        )
    )
    version = ver_result.scalar_one_or_none()
    if not version:
        raise ValueError("Version not found")

    versions = await list_versions(db, doc.id)
    if len(versions) <= 1:
        raise ValueError(ONLY_VERSION_ERROR)

    counts = await consent_counts_for_versions(db, [version_id])
    if counts.get(version_id, 0) > 0:
        raise LegalVersionDeleteBlocked(CONSENT_BLOCKED_ERROR)

    was_current = doc.current_version_id == version_id
    await db.delete(version)
    await db.flush()

    if was_current:
        remaining = await list_versions(db, doc.id)
        doc.current_version_id = remaining[0].id if remaining else None
        await db.flush()

    return doc


def user_needs_reconsent(user: User) -> bool:
    return bool(user.email or user.max_user_id)


async def get_user_consent(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> UserLegalConsent | None:
    result = await db.execute(
        select(UserLegalConsent).where(
            UserLegalConsent.user_id == user_id,
            UserLegalConsent.document_id == document_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_user_consent(
    db: AsyncSession,
    user: User,
    doc: LegalDocument,
    version_id: uuid.UUID,
    *,
    meta: ConsentMeta,
) -> UserLegalConsent:
    if doc.current_version_id != version_id:
        raise ValueError(f"Устаревшая версия документа: {doc.slug}")
    ver_result = await db.execute(
        select(LegalDocumentVersion).where(
            LegalDocumentVersion.id == version_id,
            LegalDocumentVersion.document_id == doc.id,
        )
    )
    if not ver_result.scalar_one_or_none():
        raise ValueError(f"Invalid version for {doc.slug}")

    existing = await get_user_consent(db, user.id, doc.id)
    now = datetime.now(timezone.utc)
    if existing:
        existing.version_id = version_id
        existing.consented_at = now
        existing.source = meta.source
        existing.ip_address = meta.ip_address
        existing.user_agent = meta.user_agent
        existing.consent_method = meta.consent_method
        await db.flush()
        return existing

    row = UserLegalConsent(
        user_id=user.id,
        document_id=doc.id,
        version_id=version_id,
        consented_at=now,
        source=meta.source,
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
        consent_method=meta.consent_method,
    )
    db.add(row)
    await db.flush()
    return row


async def record_consent(
    db: AsyncSession,
    user: User,
    *,
    slug: str,
    version_id: uuid.UUID,
    meta: ConsentMeta,
) -> UserLegalConsent:
    doc = await get_document_by_slug(db, slug)
    if not doc or not doc.current_version_id:
        raise ValueError(f"Document not configured: {slug}")
    return await upsert_user_consent(db, user, doc, version_id, meta=meta)


async def get_pending_consents(db: AsyncSession, user: User) -> list[PendingConsent]:
    if not user_needs_reconsent(user):
        return []

    result = await db.execute(
        select(LegalDocument)
        .where(LegalDocument.slug.in_(RECONSENT_SLUGS))
        .order_by(LegalDocument.slug)
    )
    docs = list(result.scalars().all())
    pending: list[PendingConsent] = []
    for doc in docs:
        if not doc.current_version_id:
            continue
        await db.refresh(doc, attribute_names=["current_version"])
        current = doc.current_version
        if not current:
            continue
        consent = await get_user_consent(db, user.id, doc.id)
        if consent and consent.version_id == doc.current_version_id:
            continue
        pending.append(
            PendingConsent(
                slug=doc.slug,
                title=doc.title,
                public_path=doc.public_path,
                version_id=current.id,
                version_number=current.version_number,
            )
        )
    return pending


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
    meta: ConsentMeta,
) -> None:
    mapping = {
        "privacy": privacy_version_id,
        "pd_consent": pd_consent_version_id,
    }
    for slug, version_id in mapping.items():
        await record_consent(db, user, slug=slug, version_id=version_id, meta=meta)
