
"""Narrative ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.infrastructure.database.base import Base
from backend.shared.infrastructure.database.mixins import EntityMixin


class StoryDocumentModel(Base, EntityMixin):
    __tablename__ = "story_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class NarrativeSceneModel(Base, EntityMixin):
    __tablename__ = "narrative_scenes"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence_number", name="uq_narrative_scene_seq"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    story_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("story_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    location: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    time_of_day: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    mood: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
