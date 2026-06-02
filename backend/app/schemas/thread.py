from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.message import MessageRole
from app.schemas.feedback import MessageFeedbackOut


class ThreadCreate(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    thread_id: UUID | None = None


class SourceOut(BaseModel):
    index: int
    url: str
    title: str
    snippet: str
    domain: str


class EntityImageOut(BaseModel):
    url: str
    title: str
    page_url: str
    width: int | None = None
    height: int | None = None


class MessageAttachmentOut(BaseModel):
    id: str
    filename: str
    kind: str
    url: str | None = None


class MessageOut(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    sources: list[SourceOut] | None
    images: list[EntityImageOut] | None = None
    attachments: list[MessageAttachmentOut] | None = None
    follow_up_questions: list[str] | None
    user_feedback: MessageFeedbackOut | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ThreadListItem(BaseModel):
    id: UUID
    title: str
    message_count: int
    is_saved: bool
    last_message_at: datetime

    model_config = {"from_attributes": True}


class ThreadDetail(BaseModel):
    id: UUID
    title: str
    is_saved: bool
    messages: list[MessageOut]

    model_config = {"from_attributes": True}


class ThreadUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)


class ThreadBulkDeleteIn(BaseModel):
    thread_ids: list[UUID] = Field(..., min_length=1, max_length=100)


class ThreadBulkDeleteOut(BaseModel):
    deleted: int
    not_found: int
