"""cache.db — Transient cache for generation results, embeddings, and computed metadata."""

from __future__ import annotations

import datetime
import os
from typing import Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, LargeBinary, Float, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from backend.config import get_config


class CacheBase(DeclarativeBase):
    __allow_unmapped__ = True
    pass


class Cache(CacheBase):
    """Generic key-value cache with TTL support."""
    __tablename__ = "cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(512), nullable=False, unique=True)
    cache_value = Column(Text, default="")
    value_type = Column(String(64), default="text")       # text / json / binary_path
    ttl_seconds = Column(Integer, default=3600)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, default=None)


# ============================================================
# Engine & Session
# ============================================================

_engine = None
_SessionLocal = None


def init_cache_db() -> None:
    global _engine, _SessionLocal
    config = get_config()
    db_path = config.database.cache_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    CacheBase.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)


def get_cache_session() -> Session:
    if _SessionLocal is None:
        init_cache_db()
    return _SessionLocal()
