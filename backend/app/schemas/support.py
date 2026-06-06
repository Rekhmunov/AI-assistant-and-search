from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SupportTicketCreate(BaseModel):
    message: str = Field(..., min_length=3, max_length=5000)
    source: str = Field(default="general", max_length=64)


class SupportTicketCreateOut(BaseModel):
    id: UUID
    created_at: datetime


class SupportTicketAdminOut(BaseModel):
    id: UUID
    user_id: UUID
    user_email: str | None
    user_max_user_id: int | None
    source: str
    message: str
    status: str
    created_at: datetime
    closed_at: datetime | None
