from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.legal import LegalDocumentPublicOut, LegalRegisterMetaOut, LegalRouteOut
from app.services.legal_documents import (
    document_to_public,
    get_document_by_path,
    get_document_by_slug,
    list_documents_admin,
)

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/routes", response_model=list[LegalRouteOut])
async def legal_routes(db: Annotated[AsyncSession, Depends(get_db)]):
    docs = await list_documents_admin(db)
    out: list[LegalRouteOut] = []
    for doc in docs:
        if not doc.current_version_id:
            continue
        out.append(
            LegalRouteOut(
                slug=doc.slug,
                title=doc.title,
                public_path=doc.public_path,
                version_id=doc.current_version_id,
            )
        )
    return out


@router.get("/register-meta", response_model=LegalRegisterMetaOut)
async def legal_register_meta(db: Annotated[AsyncSession, Depends(get_db)]):
    docs = await list_documents_admin(db)
    items: list[LegalRouteOut] = []
    for doc in docs:
        if doc.slug not in ("privacy", "pd_consent") or not doc.current_version_id:
            continue
        items.append(
            LegalRouteOut(
                slug=doc.slug,
                title=doc.title,
                public_path=doc.public_path,
                version_id=doc.current_version_id,
            )
        )
    return LegalRegisterMetaOut(documents=items)


@router.get("/by-path", response_model=LegalDocumentPublicOut)
async def legal_by_path(
    db: Annotated[AsyncSession, Depends(get_db)],
    path: Annotated[str, Query(min_length=1)],
):
    doc = await get_document_by_path(db, path)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await db.refresh(doc, attribute_names=["current_version"])
    public = document_to_public(doc)
    if not public:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return LegalDocumentPublicOut(
        slug=public.slug,
        title=public.title,
        public_path=public.public_path,
        version_id=public.version_id,
        version_number=public.version_number,
        content_html=public.content_html,
        updated_at=doc.updated_at,
    )


@router.get("/{slug}", response_model=LegalDocumentPublicOut)
async def legal_by_slug(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await get_document_by_slug(db, slug)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await db.refresh(doc, attribute_names=["current_version"])
    public = document_to_public(doc)
    if not public:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return LegalDocumentPublicOut(
        slug=public.slug,
        title=public.title,
        public_path=public.public_path,
        version_id=public.version_id,
        version_number=public.version_number,
        content_html=public.content_html,
        updated_at=doc.updated_at,
    )
