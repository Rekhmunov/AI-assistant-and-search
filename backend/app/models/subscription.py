import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    CANCELED = "canceled"
    FAILED = "failed"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    yookassa_payment_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        ENUM(
            SubscriptionStatus,
            name="subscription_status_enum",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SubscriptionStatus.PENDING,
    )
    amount_rub: Mapped[int] = mapped_column(default=299)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="subscriptions")
