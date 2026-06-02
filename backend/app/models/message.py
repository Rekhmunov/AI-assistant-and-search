import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(
        ENUM(
            MessageRole,
            name="message_role_enum",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
    )
    content: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    images: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    attachments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    follow_up_questions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    debug_trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped["Thread"] = relationship(back_populates="messages")
