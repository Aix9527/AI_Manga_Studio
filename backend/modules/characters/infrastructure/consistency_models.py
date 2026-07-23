
"""ORM models for character consistency data."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.infrastructure.database.base import Base
from backend.shared.infrastructure.database.mixins import EntityMixin


class IdentityBoardModel(Base, EntityMixin):
    __tablename__ = "identity_boards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    gender_presentation: Mapped[str] = mapped_column(String(50), nullable=False)
    age_stage: Mapped[str] = mapped_column(String(50), nullable=False)
    ethnicity_style: Mapped[str] = mapped_column(String(50), nullable=False)
    core_face_shape: Mapped[str] = mapped_column(String(50), nullable=False)
    signature_traits_json: Mapped[str] = mapped_column(Text, nullable=False)
    board_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AppearanceSheetModel(Base, EntityMixin):
    __tablename__ = "appearance_sheets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    character_version_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hair_color: Mapped[str] = mapped_column(String(50), nullable=False)
    hair_style: Mapped[str] = mapped_column(String(100), nullable=False)
    eye_color: Mapped[str] = mapped_column(String(50), nullable=False)
    build: Mapped[str] = mapped_column(String(50), nullable=False)
    skin_tone: Mapped[str | None] = mapped_column(String(50))
    height_impression: Mapped[str | None] = mapped_column(String(50))
    sheet_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ConsistencyCheckModel(Base, EntityMixin):
    __tablename__ = "consistency_checks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    shot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    asset_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    passed: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    drift_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    discrepancies_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    reference_asset_version_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WardrobeSetModel(Base, EntityMixin):
    __tablename__ = "wardrobe_sets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    garments_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    accessories_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    variants_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    set_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
