"""DatabaseManager initialization tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.platform.infrastructure.database import DatabaseManager
from backend.modules.platform.infrastructure.settings import AppSettings


@pytest.mark.asyncio
async def test_non_sqlite_url_does_not_reference_db_path() -> None:
    settings = AppSettings(
        database_url="postgresql+asyncpg://user:pass@localhost/test",
        environment="test",
    )
    manager = DatabaseManager(settings)

    engine = MagicMock()
    engine.dispose = AsyncMock()

    with (
        patch(
            "backend.modules.platform.infrastructure.database."
            "create_database_engine",
            return_value=engine,
        ),
        patch(
            "backend.modules.platform.infrastructure.database."
            "create_session_factory",
            return_value=MagicMock(),
        ),
        patch.object(
            manager,
            "_create_tables",
            new=AsyncMock(),
        ),
    ):
        await manager.init()

    assert manager.initialized is True


@pytest.mark.asyncio
async def test_initialization_failure_cleans_up_engine_state() -> None:
    settings = AppSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="test",
    )
    manager = DatabaseManager(settings)

    engine = MagicMock()
    engine.dispose = AsyncMock()

    with (
        patch(
            "backend.modules.platform.infrastructure.database."
            "create_database_engine",
            return_value=engine,
        ),
        patch(
            "backend.modules.platform.infrastructure.database."
            "create_session_factory",
            return_value=MagicMock(),
        ),
        patch.object(
            manager,
            "_create_tables",
            new=AsyncMock(side_effect=RuntimeError("schema failed")),
        ),
    ):
        with pytest.raises(RuntimeError, match="schema failed"):
            await manager.init()

    engine.dispose.assert_awaited_once()
    assert manager.initialized is False


@pytest.mark.asyncio
async def test_sqlite_memory_database_initializes() -> None:
    settings = AppSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="test",
    )
    manager = DatabaseManager(settings)

    await manager.init()

    try:
        assert manager.initialized is True
        assert await manager.ping() is True
    finally:
        await manager.close()

    assert manager.initialized is False
