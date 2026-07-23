"""Application lifecycle (startup / shutdown)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.container_builder import build_container
from backend.modules.platform.infrastructure.database import DatabaseManager
from backend.modules.platform.infrastructure.settings import AppSettings


def create_lifespan(
    settings: AppSettings,
    database_manager: DatabaseManager,
):
    """Create a FastAPI lifespan context manager."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await database_manager.init()
        container = await build_container(settings, database_manager)
        app.state.container = container

        try:
            yield
        finally:
            # Worker supervision is not started until the runtime API is
            # implemented. Database shutdown is always safe and deterministic.
            await database_manager.close()

    return lifespan
