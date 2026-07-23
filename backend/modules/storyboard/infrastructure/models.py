
"""Storyboard ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.infrastructure.database.base import Base
from backend.shared.infrastructure.database.mixins import EntityMixin


class StoryboardSceneModel(Base, EntityMixin):
    __tablename__ = "storyboard_scenes"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence_number", name="uq_storyboard_scene_seq"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    narrative_scene_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("narrative_scenes.id", ondelete="SET NULL")
    )

    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ShotModel(Base, EntityMixin):
    __tablename__ = "shots"
    __table_args__ = (
        UniqueConstraint("scene_id", "shot_number", name="uq_shot_number"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    scene_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("storyboard_scenes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    shot_number: Mapped[int] = mapped_column(Integer, nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    framing: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    camera_angle: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    camera_motion: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    dialog: Mapped[str] = mapped_column(Text, nullable=False, default="")

    frozen_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ShotCharacterModel(Base):
    __tablename__ = "shot_characters"

    shot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shots.id", ondelete="CASCADE"), primary_key=True
    )

    character_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )

    pose: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    expression: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    position: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    scale: Mapped[str] = mapped_column(String(50), nullable=False, default="")
