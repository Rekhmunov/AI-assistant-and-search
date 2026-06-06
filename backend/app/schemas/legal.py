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
    current_version: LegalVersionOut | None = None
    versions: list[LegalVersionOut] = Field(default_factory=list)


class LegalDocumentUpdate(BaseModel):
    content_html: str = Field(..., min_length=1)
    public_path: str | None = Field(default=None, max_length=255)


class LegalDocumentPublicOut(BaseModel):
    slug: str
    title: str
    public_path: str
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
