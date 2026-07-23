
"""Media asset ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.infrastructure.database.base import Base
from backend.shared.infrastructure.database.mixins import EntityMixin


class AssetModel(Base, EntityMixin):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(300), nullable=False)

    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    current_version_id: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AssetVersionModel(Base, EntityMixin):
    __tablename__ = "asset_versions"
    __table_args__ = (
        UniqueConstraint("asset_id", "version_number", name="uq_asset_version_num"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)

    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AssetLineageModel(Base):
    __tablename__ = "asset_lineage"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    source_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    derived_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False
    )

    relationship: Mapped[str] = mapped_column(String(50), nullable=False)
    meta: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class AssetReviewModel(Base, EntityMixin):
    __tablename__ = "asset_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    asset_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    reviewer_id: Mapped[str] = mapped_column(String(64), nullable=False)

    decision: Mapped[str] = mapped_column(String(50), nullable=False)

    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
