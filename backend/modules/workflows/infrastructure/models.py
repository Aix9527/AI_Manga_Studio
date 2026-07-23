
"""Workflows ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.infrastructure.database.base import Base
from backend.shared.infrastructure.database.mixins import EntityMixin


class JobModel(Base, EntityMixin):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    job_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)

    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    leased_by: Mapped[str | None] = mapped_column(String(100), index=True)

    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    error_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class LeaseRecordModel(Base, EntityMixin):
    __tablename__ = "lease_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    worker_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    lease_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class HeartbeatModel(Base, EntityMixin):
    __tablename__ = "worker_heartbeats"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    worker_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="alive")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
