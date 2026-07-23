"""Application lifecycle (startup / shutdown)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.container import ApplicationContainer


def create_lifespan(container: ApplicationContainer):
    """Create a FastAPI lifespan context manager."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
        await container.platform.startup()
        await container.workflows.recover_expired_leases()
        await container.workflows.start_workers()

        try:
            yield
        finally:
            await container.workflows.stop_workers()
            await container.platform.shutdown()

    return lifespan
