"""projects.db — Projects, chapters, and shot pipeline state."""

from __future__ import annotations

import datetime
import os
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker, Session

from backend.config import get_config


class ProjectBase(DeclarativeBase):
    __allow_unmapped__ = True
    pass


class Project(ProjectBase):
    """Top-level manga / novel adaptation project."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    description = Column(Text, default="")
    status = Column(String(32), default="pending")
    source_type = Column(String(32), default="novel")
    source_path = Column(String(1024), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    chapters = relationship("Chapter", back_populates="project", cascade="all, delete-orphan")


class Chapter(ProjectBase):
    """A chapter inside a project."""
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    index = Column(Integer, nullable=False)
    title = Column(String(256), default="")
    raw_text = Column(Text, default="")
    parsed_json = Column(JSON, default=None)
    status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="chapters")
    shots = relationship("Shot", back_populates="chapter", cascade="all, delete-orphan")


class Shot(ProjectBase):
    """Single shot / frame with pipeline status tracking.

    Status flow:  等待 → 生成中 → 成功 / 失败
    On 失败: auto-retry (reset to 生成中, increment retry_count).
    """
    __tablename__ = "shots"

    # -- identity --
    id = Column(Integer, primary_key=True, autoincrement=True)
    shot_id = Column(String(64), nullable=False, default="")   # e.g. Shot001
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=False)
    index = Column(Integer, nullable=False)

    # -- tracking --
    json_path = Column(String(1024), default="")     # path to unified shot JSON
    status = Column(String(32), default="waiting")
    retry_count = Column(Integer, default=0)
    retry_max = Column(Integer, default=3)
    error_message = Column(Text, default="")

    # -- generation params --
    shot_type = Column(String(64), default="medium")
    camera_instruction = Column(Text, default="")
    prompt_positive = Column(Text, default="")
    prompt_negative = Column(Text, default="")
    character_ids = Column(JSON, default=list)
    scene_id = Column(Integer, nullable=True)
    dialogue = Column(Text, default="")
    motion_description = Column(Text, default="")
    emotion_description = Column(Text, default="")

    # -- outputs --
    image_path = Column(String(1024), default="")
    video_path = Column(String(1024), default="")
    thumbnail_path = Column(String(1024), default="")
    quality_score = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    chapter = relationship("Chapter", back_populates="shots")


# ============================================================
# Engine & Session
# ============================================================

_engine = None
_SessionLocal = None


def init_projects_db() -> None:
    global _engine, _SessionLocal
    config = get_config()
    db_path = config.database.projects_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    ProjectBase.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)


def get_projects_session() -> Session:
    if _SessionLocal is None:
        init_projects_db()
    return _SessionLocal()
