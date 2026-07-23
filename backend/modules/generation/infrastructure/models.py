
"""Generation ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.infrastructure.database.base import Base
from backend.shared.infrastructure.database.mixins import EntityMixin


class GenerationRequestModel(Base, EntityMixin):
    __tablename__ = "generation_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    shot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shots.id", ondelete="CASCADE"), nullable=False, index=True
    )

    purpose: Mapped[str] = mapped_column(String(100), nullable=False)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")

    compiled_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")

    parameters_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class GenerationPlanModel(Base, EntityMixin):
    __tablename__ = "generation_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    request_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider_id: Mapped[str] = mapped_column(String(100), nullable=False)

    compiled_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)

    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class GenerationAttemptModel(Base, EntityMixin):
    __tablename__ = "generation_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    plan_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    request_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    provider_id: Mapped[str] = mapped_column(String(100), nullable=False)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")

    remote_task_id: Mapped[str | None] = mapped_column(String(200))

    output_asset_id: Mapped[str | None] = mapped_column(String(64))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class GenerationCandidateModel(Base, EntityMixin):
    __tablename__ = "generation_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    attempt_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    request_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )

    asset_version_id: Mapped[str] = mapped_column(String(64), nullable=False)

    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
