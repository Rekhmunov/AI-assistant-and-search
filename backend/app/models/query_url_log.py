"""Память «нормализованный запрос → удачный URL» (уровень 2 индекса)."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QueryUrlLog(Base):
    __tablename__ = "query_url_log"
    __table_args__ = (
        UniqueConstraint("query_key", "url_hash", name="uq_query_url_log_key_url"),
        Index("ix_query_url_log_query_key", "query_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    query_key: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(512), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
