"""scenes.db — Scene / background memory for consistent environment generation."""

from __future__ import annotations

import datetime
import os
from typing import Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from backend.config import get_config


class SceneBase(DeclarativeBase):
    __allow_unmapped__ = True
    pass


class Scene(SceneBase):
    """Persistent scene / background memory.

    Fields:
        id        — 场景ID
        prompt    — 背景Prompt
        lighting  — 灯光
        weather   — 天气
        time      — 时间
    """
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    description = Column(Text, default="")

    # -- generation --
    prompt = Column(Text, default="")
    lighting = Column(String(256), default="natural")
    weather = Column(String(64), default="clear")
    time_of_day = Column(String(64), default="day")

    # -- control --
    controlnet_type = Column(String(64), default="")
    controlnet_path = Column(String(1024), default="")
    reference_images = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


# ============================================================
# Engine & Session
# ============================================================

_engine = None
_SessionLocal = None


def init_scenes_db() -> None:
    global _engine, _SessionLocal
    config = get_config()
    db_path = config.database.scenes_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    SceneBase.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)


def get_scenes_session() -> Session:
    if _SessionLocal is None:
        init_scenes_db()
    return _SessionLocal()
