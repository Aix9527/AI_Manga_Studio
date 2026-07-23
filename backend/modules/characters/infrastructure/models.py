
"""Character ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.infrastructure.database.base import Base
from backend.shared.infrastructure.database.mixins import EntityMixin


class CharacterModel(Base, EntityMixin):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    role: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    personality: Mapped[str] = mapped_column(Text, nullable=False, default="")

    background: Mapped[str] = mapped_column(Text, nullable=False, default="")

    appearance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    current_version_id: Mapped[str | None] = mapped_column(String(64))

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CharacterVersionModel(Base, EntityMixin):
    __tablename__ = "character_versions"
    __table_args__ = (
        UniqueConstraint("character_id", "version_number", name="uq_char_version_num"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    character_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)

    change_description: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
