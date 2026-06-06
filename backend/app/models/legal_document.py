import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LegalDocument(Base):
    __tablename__ = "legal_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    public_path: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("legal_document_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    versions: Mapped[list["LegalDocumentVersion"]] = relationship(
        back_populates="document",
        foreign_keys="LegalDocumentVersion.document_id",
        cascade="all, delete-orphan",
        order_by="LegalDocumentVersion.version_number.desc()",
    )
    current_version: Mapped["LegalDocumentVersion | None"] = relationship(
        foreign_keys=[current_version_id],
        post_update=True,
    )


class LegalDocumentVersion(Base):
    __tablename__ = "legal_document_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("legal_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    admin_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    document: Mapped["LegalDocument"] = relationship(
        back_populates="versions",
        foreign_keys=[document_id],
    )


class UserLegalConsent(Base):
    __tablename__ = "user_legal_consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("legal_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("legal_document_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
