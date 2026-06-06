from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_permissions import require_permission
from app.models.admin_user import AdminUser
from app.schemas.legal import LegalDocumentAdminOut, LegalDocumentUpdate, LegalVersionOut
from app.services.admin_audit import log_admin_action
from app.services.legal_documents import (
    ensure_default_documents,
    get_document_by_slug,
    list_documents_admin,
    list_versions,
    save_document_version,
)

router = APIRouter(prefix="/legal", tags=["admin-legal"])


def _version_out(v) -> LegalVersionOut:
    return LegalVersionOut(
        id=v.id,
        version_number=v.version_number,
        content_html=v.content_html,
        created_at=v.created_at,
        admin_email=v.admin_email,
    )


@router.get("", response_model=list[LegalDocumentAdminOut])
async def list_legal_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("legal:read")),
):
    docs = await list_documents_admin(db)
    if not docs:
        await ensure_default_documents(db)
        docs = await list_documents_admin(db)
    out: list[LegalDocumentAdminOut] = []
    for doc in docs:
        await db.refresh(doc, attribute_names=["current_version"])
        versions = await list_versions(db, doc.id)
        current = doc.current_version
        out.append(
            LegalDocumentAdminOut(
                slug=doc.slug,
                title=doc.title,
                public_path=doc.public_path,
                current_version=_version_out(current) if current else None,
                versions=[_version_out(v) for v in versions],
            )
        )
    return out


@router.get("/{slug}", response_model=LegalDocumentAdminOut)
async def get_legal_document(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("legal:read")),
):
    doc = await get_document_by_slug(db, slug)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await db.refresh(doc, attribute_names=["current_version"])
    versions = await list_versions(db, doc.id)
    current = doc.current_version
    return LegalDocumentAdminOut(
        slug=doc.slug,
        title=doc.title,
        public_path=doc.public_path,
        current_version=_version_out(current) if current else None,
        versions=[_version_out(v) for v in versions],
    )


@router.put("/{slug}", response_model=LegalDocumentAdminOut)
async def update_legal_document(
    slug: str,
    body: LegalDocumentUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("legal:write"))],
):
    try:
        version = await save_document_version(
            db,
            slug=slug,
            content_html=body.content_html,
            public_path=body.public_path,
            admin=admin,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    await log_admin_action(
        db,
        admin=admin,
        action=f"legal.{slug}.update",
        details={"version": version.version_number, "public_path": body.public_path},
        request=request,
    )
    await db.commit()

    doc = await get_document_by_slug(db, slug)
    assert doc is not None
    await db.refresh(doc, attribute_names=["current_version"])
    versions = await list_versions(db, doc.id)
    current = doc.current_version
    return LegalDocumentAdminOut(
        slug=doc.slug,
        title=doc.title,
        public_path=doc.public_path,
        current_version=_version_out(current) if current else None,
        versions=[_version_out(v) for v in versions],
    )
