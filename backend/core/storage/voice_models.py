from __future__ import annotations

from sqlalchemy import (
    String,
    Text,
    Boolean
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column
)

from .database import Base


class VoiceAssetRecord(Base):
    """角色声音资产（GPT-SoVITS IP 声音库）"""

    __tablename__="voice_assets"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    character_id: Mapped[str] = mapped_column(
        String(64)
    )


    provider: Mapped[str] = mapped_column(
        String(64)
    )


    reference_audio: Mapped[str] = mapped_column(
        Text
    )


    embedding_path: Mapped[str] = mapped_column(
        Text,
        default=""
    )


    version: Mapped[str] = mapped_column(
        String(32),
        default="v1"
    )


    sha256: Mapped[str] = mapped_column(
        String(128),
        default=""
    )


    frozen: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )


class VoiceVersionRecord(Base):
    """声音资产版本（角色 100 集同声可追踪）"""

    __tablename__="voice_versions"


    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )


    asset_id: Mapped[str] = mapped_column(
        String(64)
    )


    character_id: Mapped[str] = mapped_column(
        String(64)
    )


    version: Mapped[str] = mapped_column(
        String(32)
    )


    path: Mapped[str] = mapped_column(
        Text
    )


    sha256: Mapped[str] = mapped_column(
        String(128),
        default=""
    )
