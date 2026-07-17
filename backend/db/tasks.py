"""tasks.db — Generation task queue."""

from __future__ import annotations

import datetime
import os
from typing import Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from backend.config import get_config


class TaskBase(DeclarativeBase):
    __allow_unmapped__ = True
    pass


class Task(TaskBase):
    """Generation task in the pipeline queue.

    task_type: generate_image / generate_video / lipsync / voice / merge
    status:    queued / running / completed / failed
    """
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shot_id = Column(String(64), nullable=False)
    task_type = Column(String(64), nullable=False)
    priority = Column(Integer, default=0)
    status = Column(String(32), default="queued")
    payload = Column(JSON, default=dict)
    result = Column(JSON, default=None)
    error_message = Column(Text, default="")
    started_at = Column(DateTime, default=None)
    completed_at = Column(DateTime, default=None)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ============================================================
# Engine & Session
# ============================================================

_engine = None
_SessionLocal = None


def init_tasks_db() -> None:
    global _engine, _SessionLocal
    config = get_config()
    db_path = config.database.tasks_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    TaskBase.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)


def get_tasks_session() -> Session:
    if _SessionLocal is None:
        init_tasks_db()
    return _SessionLocal()
