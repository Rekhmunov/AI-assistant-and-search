from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.request_meta import consent_request_meta
from app.core.request_security import verify_allowed_origin
from app.models.user import User
from app.schemas.legal import (
    LegalConsentRequest,
    LegalConsentStatusOut,
    LegalDocumentPublicOut,
    LegalRegisterMetaOut,
    LegalRouteOut,
    PendingConsentOut,
)
from app.services.legal_documents import (
    ConsentMeta,
    document_to_public,
    ensure_default_documents,
    get_document_by_path,
    get_document_by_slug,
    get_pending_consents,
    list_documents_admin,
    record_consent,
)

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/routes", response_model=list[LegalRouteOut])
async def legal_routes(db: Annotated[AsyncSession, Depends(get_db)]):
    await ensure_default_documents(db)
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
    await ensure_default_documents(db)
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
        meta_title=doc.meta_title,
        meta_description=doc.meta_description,
        version_id=public.version_id,
        version_number=public.version_number,
        content_html=public.content_html,
        updated_at=doc.updated_at,
    )


@router.get("/consent-status", response_model=LegalConsentStatusOut)
async def legal_consent_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    pending = await get_pending_consents(db, user)
    return LegalConsentStatusOut(
        pending=[
            PendingConsentOut(
                slug=item.slug,
                title=item.title,
                public_path=item.public_path,
                version_id=item.version_id,
                version_number=item.version_number,
            )
            for item in pending
        ]
    )


@router.post("/consent", status_code=status.HTTP_204_NO_CONTENT)
async def legal_record_consent(
    request: Request,
    body: LegalConsentRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    verify_allowed_origin(request)
    ip_address, ua = consent_request_meta(request)
    meta = ConsentMeta(
        source=body.source,
        consent_method=body.consent_method,
        ip_address=ip_address,
        user_agent=ua,
    )
    try:
        for item in body.consents:
            await record_consent(db, user, slug=item.slug, version_id=item.version_id, meta=meta)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()


@router.get("/{slug}", response_model=LegalDocumentPublicOut)
async def legal_by_slug(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await ensure_default_documents(db)
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
        meta_title=doc.meta_title,
        meta_description=doc.meta_description,
        version_id=public.version_id,
        version_number=public.version_number,
        content_html=public.content_html,
        updated_at=doc.updated_at,
    )
