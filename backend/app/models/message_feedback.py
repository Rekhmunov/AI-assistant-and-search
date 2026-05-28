"""Оценка ответа ассистента (👍 / 👎)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FeedbackRating(str, enum.Enum):
    UP = "up"
    DOWN = "down"


class FeedbackReasonCode(str, enum.Enum):
    OUTDATED = "outdated"
    INACCURATE = "inaccurate"
    WRONG_SOURCES = "wrong_sources"
    OTHER = "other"


FEEDBACK_REASON_LABELS: dict[str, str] = {
    FeedbackReasonCode.OUTDATED.value: "Устарело",
    FeedbackReasonCode.INACCURATE.value: "Неточно",
    FeedbackReasonCode.WRONG_SOURCES.value: "Неверные источники",
    FeedbackReasonCode.OTHER.value: "Другое",
}


class MessageFeedback(Base):
    __tablename__ = "message_feedback"
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_message_feedback_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    rating: Mapped[FeedbackRating] = mapped_column(
        ENUM(
            FeedbackRating,
            name="message_feedback_rating_enum",
            create_type=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
    )
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
