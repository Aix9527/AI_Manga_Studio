
"""Database manager with auto table creation."""

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.modules.platform.infrastructure.settings import AppSettings
from backend.shared.infrastructure.database.engine import create_database_engine
from backend.shared.infrastructure.database.session import create_session_factory

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database engine, session factory, and schema initialization."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("DatabaseManager not initialized. Call init() first.")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager not initialized. Call init() first.")
        return self._session_factory

    async def init(self) -> None:
        """Initialize database engine and session factory."""
        db_path = self._settings.database_path()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._engine = create_database_engine(f"sqlite+aiosqlite:///{db_path}")
        self._session_factory = create_session_factory(self._engine)

        await self._create_tables()
        logger.info("DatabaseManager initialized at %s", db_path)

    async def _create_tables(self) -> None:
        """Auto-create all tables from registered ORM models."""
        # Import all models to ensure they are registered with Base.metadata
        import backend.modules.projects.infrastructure.models  # noqa: F401
        import backend.modules.narrative.infrastructure.models  # noqa: F401
        import backend.modules.characters.infrastructure.models  # noqa: F401
        import backend.modules.storyboard.infrastructure.models  # noqa: F401
        import backend.modules.media.infrastructure.models  # noqa: F401
        import backend.modules.generation.infrastructure.models  # noqa: F401
        import backend.modules.workflows.infrastructure.models  # noqa: F401
        import backend.modules.characters.infrastructure.consistency_models  # noqa: F401
        import backend.shared.infrastructure.database.base  # noqa: F401

        from backend.shared.infrastructure.database.base import Base

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database tables created successfully")

    async def close(self) -> None:
        """Dispose the database engine."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("DatabaseManager closed")
