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
    share_url: str | None = None
    ttl_hours: int | None = None
    expires_at: datetime | None = None
    title: str | None = None
    content: str | None = None


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
    thread_type: str = "search"
    agent_seq: int | None = None
    message_count: int
    is_saved: bool
    pinned_at: datetime | None = None
    last_message_at: datetime

    model_config = {"from_attributes": True}


class ThreadDetail(BaseModel):
    id: UUID
    title: str
    thread_type: str = "search"
    agent_seq: int | None = None
    is_saved: bool
    pinned_at: datetime | None = None
    messages: list[MessageOut]
    agent_config: dict | None = None  # poster_* fields for agent threads

    model_config = {"from_attributes": True}


class ThreadUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    pinned: bool | None = None


class ThreadBulkDeleteIn(BaseModel):
    thread_ids: list[UUID] = Field(..., min_length=1, max_length=100)


class ThreadBulkDeleteOut(BaseModel):
    deleted: int
    not_found: int


class AnswerStatusOut(BaseModel):
    """Состояние незавершённого ответа в треде (polling при возврате на страницу)."""

    pending: bool
    active: bool
    stale: bool
    active_age_sec: float | None = None
    phase: str | None = None
    needs_search: bool | None = None
    custom_status: str | None = None
    user_message_id: UUID | None = None
    query: str | None = None
