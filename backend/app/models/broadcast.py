import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BroadcastStatus(str, enum.Enum):
    DRAFT = "draft"
    SENDING = "sending"
    DONE = "done"
    FAILED = "failed"


class BroadcastAudience(str, enum.Enum):
    ALL = "all"
    FREE = "free"
    PRO = "pro"


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text: Mapped[str] = mapped_column(Text)
    audience: Mapped[BroadcastAudience] = mapped_column(
        Enum(BroadcastAudience, name="broadcast_audience_enum"), default=BroadcastAudience.ALL
    )
    status: Mapped[BroadcastStatus] = mapped_column(
        Enum(BroadcastStatus, name="broadcast_status_enum"), default=BroadcastStatus.DRAFT
    )
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BroadcastLogStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"


class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("broadcasts.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[BroadcastLogStatus] = mapped_column(Enum(BroadcastLogStatus, name="broadcast_log_status_enum"))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
