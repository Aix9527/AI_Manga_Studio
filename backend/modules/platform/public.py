"""Platform module public API — database lifecycle, health checks."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.modules.platform.infrastructure.database import DatabaseManager
from backend.modules.platform.infrastructure.settings import AppSettings


@dataclass(slots=True)
class PlatformModuleApi:
    """Public interface for platform-level operations."""

    _database: DatabaseManager
    _settings: AppSettings
    _session_factory: async_sessionmaker

    async def startup(self) -> None:
        await self._database.startup()

    async def shutdown(self) -> None:
        await self._database.shutdown()

    async def health(self) -> dict[str, Any]:
        db_ok = await self._database.ping()
        return {
            "status": "ok" if db_ok else "degraded",
            "components": {
                "database": "ok" if db_ok else "down",
            },
            "environment": self._settings.environment,
        }

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @property
    def session_factory(self) -> async_sessionmaker:
        return self._session_factory
