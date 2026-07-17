"""characters.db — Character persistence with stable identity for AI generation."""

from __future__ import annotations

import datetime
import os
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from backend.config import get_config


class CharacterBase(DeclarativeBase):
    __allow_unmapped__ = True
    pass


class Character(CharacterBase):
    """Persistent character identity for consistent AI generation.

    Fields:
        id           — 角色ID (auto-increment)
        name         — 角色名
        prompt       — 角色Prompt (稳定生图描述)
        seed         — 固定Seed (保证同角色一致)
        face_image   — 参考图路径
        voice        — 音色标识
        emotion      — 默认情绪
    """
    __tablename__ = "characters"

    # -- identity --
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    alias = Column(String(256), default="")

    # -- generation anchor --
    prompt = Column(Text, default="")
    seed = Column(Integer, default=0)
    face_image = Column(String(1024), default="")

    # -- audio --
    voice = Column(String(256), default="")
    voice_model = Column(String(256), default="")

    # -- state --
    emotion = Column(String(64), default="neutral")

    # -- extras --
    gender = Column(String(16), default="unknown")
    age_estimate = Column(Integer, default=0)
    personality = Column(Text, default="")
    reference_images = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


# ============================================================
# Engine & Session
# ============================================================

_engine = None
_SessionLocal = None


def init_characters_db() -> None:
    global _engine, _SessionLocal
    config = get_config()
    db_path = config.database.characters_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    CharacterBase.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)


def get_characters_session() -> Session:
    if _SessionLocal is None:
        init_characters_db()
    return _SessionLocal()
