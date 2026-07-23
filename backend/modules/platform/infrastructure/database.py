
"""Database manager with auto table creation."""

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
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
    def initialized(self) -> bool:
        return self._engine is not None and self._session_factory is not None

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
        """Initialize the database engine, session factory, and schema."""
        if self.initialized:
            return

        database_url = self._settings.database_url
        parsed_url = make_url(database_url)

        if parsed_url.get_backend_name() == "sqlite":
            database_name = parsed_url.database

            if database_name and database_name != ":memory:":
                database_path = Path(database_name).expanduser()

                if not database_path.is_absolute():
                    database_path = Path.cwd() / database_path

                database_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

        self._engine = create_database_engine(database_url)
        self._session_factory = create_session_factory(self._engine)

        try:
            await self._create_tables()
        except Exception:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            raise

        logger.info(
            "DatabaseManager initialized using %s",
            parsed_url.render_as_string(hide_password=True),
        )

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

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database tables created successfully")

    async def ping(self) -> bool:
        """Return whether the database accepts a simple query."""
        if not self.initialized:
            return False
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception:
            logger.exception("Database health check failed")
            return False

    async def close(self) -> None:
        """Dispose the database engine."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("DatabaseManager closed")
