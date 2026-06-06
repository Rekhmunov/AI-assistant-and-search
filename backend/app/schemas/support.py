from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SupportTicketCreate(BaseModel):
    message: str = Field(..., min_length=3, max_length=5000)
    source: str = Field(default="general", max_length=64)


class SupportTicketCreateOut(BaseModel):
    id: UUID
    created_at: datetime


class SupportTicketReplyOut(BaseModel):
    id: UUID
    author_type: str
    admin_email: str | None = None
    message: str
    created_at: datetime


class SupportTicketUserOut(BaseModel):
    id: UUID
    source: str
    message: str
    status: str
    created_at: datetime
    closed_at: datetime | None = None
    replies: list[SupportTicketReplyOut] = Field(default_factory=list)


class SupportTicketAdminOut(BaseModel):
    id: UUID
    user_id: UUID
    user_email: str | None
    user_max_user_id: int | None
    source: str
    message: str
    status: str
    created_at: datetime
    closed_at: datetime | None = None
    yookassa_payment_id: str | None = None
    payment_amount_rub: int | None = None
    subscription_id: UUID | None = None
    replies: list[SupportTicketReplyOut] = Field(default_factory=list)


class SupportTicketReplyCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class SupportTicketStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|in_progress|closed)$")
