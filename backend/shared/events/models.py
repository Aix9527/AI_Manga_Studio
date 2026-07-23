"""Outbox event ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.infrastructure.database.base import Base


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    event_type: Mapped[str] = mapped_column(String(120), nullable=False)

    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)

    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)

    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)

    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    correlation_id: Mapped[str | None] = mapped_column(String(64))

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_error: Mapped[str | None] = mapped_column(Text)
