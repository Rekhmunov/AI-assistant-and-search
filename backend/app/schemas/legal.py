from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LegalVersionOut(BaseModel):
    id: UUID
    version_number: int
    content_html: str
    created_at: datetime
    admin_email: str | None = None
    consent_count: int = 0


class LegalDocumentAdminOut(BaseModel):
    slug: str
    title: str
    public_path: str
    meta_title: str | None = None
    meta_description: str | None = None
    current_version: LegalVersionOut | None = None
    versions: list[LegalVersionOut] = Field(default_factory=list)


class LegalDocumentUpdate(BaseModel):
    content_html: str = Field(..., min_length=1)
    public_path: str | None = Field(default=None, max_length=255)
    meta_title: str | None = Field(default=None, max_length=255)
    meta_description: str | None = Field(default=None, max_length=500)


class LegalDocumentPublicOut(BaseModel):
    slug: str
    title: str
    public_path: str
    meta_title: str | None = None
    meta_description: str | None = None
    version_id: UUID
    version_number: int
    content_html: str
    updated_at: datetime | None = None


class LegalRouteOut(BaseModel):
    slug: str
    title: str
    public_path: str
    version_id: UUID


class LegalRegisterMetaOut(BaseModel):
    documents: list[LegalRouteOut]


class PendingConsentOut(BaseModel):
    slug: str
    title: str
    public_path: str
    version_id: UUID
    version_number: int


class LegalConsentStatusOut(BaseModel):
    pending: list[PendingConsentOut]


class LegalConsentItem(BaseModel):
    slug: str
    version_id: UUID


class LegalConsentRequest(BaseModel):
    consents: list[LegalConsentItem] = Field(..., min_length=1)
    source: str = Field(..., min_length=1, max_length=64)
    consent_method: str = Field(..., min_length=1, max_length=32)
