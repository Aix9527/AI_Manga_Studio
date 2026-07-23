"""
Database Session & Manager (Part 13)

Provides async SQLAlchemy session management with connection pooling,
transaction scoping, and migration support. Uses SQLite for MVP with
a migration path to PostgreSQL.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from backend.config import get_settings


logger = logging.getLogger(__name__)


# ── Base ─────────────────────────────────────────────────────────────────

Base = declarative_base()


# ── Database Manager ────────────────────────────────────────────────────


class DatabaseManager:
    """
    Manages async database connections, session factories, and migrations.

    MVP: SQLite via aiosqlite
    Future: PostgreSQL via asyncpg
    """

    def __init__(self, url: Optional[str] = None) -> None:
        settings = get_settings()
        self.url = url or settings.database_url
        self._engine = None
        self._session_factory = None

    async def initialize(self) -> None:
        """Create engine and session factory, run migrations."""
        self._engine = create_async_engine(
            self.url,
            echo=get_settings().database_echo,
            pool_size=get_settings().database_pool_size,
        )

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Auto-create tables for MVP
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database initialized: %s", self.url.split("://")[0])

    async def dispose(self) -> None:
        """Close all connections and dispose engine."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connections closed")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Get an async session with automatic commit/rollback."""
        if not self._session_factory:
            raise RuntimeError("Database not initialized")

        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @property
    def session_factory(self) -> async_sessionmaker:
        if not self._session_factory:
            raise RuntimeError("Database not initialized")
        return self._session_factory

    @property
    def engine(self):
        if not self._engine:
            raise RuntimeError("Database not initialized")
        return self._engine
