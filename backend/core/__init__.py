"""
AI Manga Studio - Application Core

Central application bootstrap, dependency injection container,
and lifecycle management. Serves as the composition root that
wires together all layers: API, orchestration, agents, providers,
workflow, memory, and infrastructure.

Architecture: DDD + Agent + Workflow + Provider + Event
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from backend.config.settings import Settings
from backend.database.session import DatabaseManager
from backend.events.bus import EventBus
from backend.orchestration.job_manager import JobManager
from backend.workflow.compiler import WorkflowCompiler
from backend.agents.registry import AgentRegistry


logger = logging.getLogger(__name__)


@dataclass
class Application:
    """
    Composition root for AI Manga Studio.

    Owns the lifecycle of all major subsystems and provides
    the dependency injection container for FastAPI and workers.
    """

    settings: Settings = field(default_factory=Settings)
    _db: Optional[DatabaseManager] = None
    _event_bus: Optional[EventBus] = None
    _job_manager: Optional[JobManager] = None
    _agent_registry: Optional[AgentRegistry] = None
    _workflow_compiler: Optional[WorkflowCompiler] = None

    # ── Lifecycle ──────────────────────────────────────────

    async def startup(self) -> None:
        """Initialize all subsystems in dependency order."""
        logger.info("Starting AI Manga Studio application...")

        # 1. Database
        self._db = DatabaseManager(self.settings.database_url)
        await self._db.initialize()

        # 2. Event Bus
        self._event_bus = EventBus()
        await self._event_bus.start()

        # 3. Agent Registry
        self._agent_registry = AgentRegistry()
        await self._agent_registry.discover()

        # 4. Workflow Compiler
        self._workflow_compiler = WorkflowCompiler(
            registry=self._agent_registry
        )

        # 5. Job Manager (orchestration)
        self._job_manager = JobManager(
            event_bus=self._event_bus,
            compiler=self._workflow_compiler,
        )
        await self._job_manager.start()

        logger.info("Application startup complete.")

    async def shutdown(self) -> None:
        """Gracefully shutdown all subsystems in reverse order."""
        logger.info("Shutting down application...")

        if self._job_manager:
            await self._job_manager.shutdown()
        if self._event_bus:
            await self._event_bus.stop()
        if self._db:
            await self._db.dispose()

        logger.info("Application shutdown complete.")

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[Application]:
        """ASGI lifespan context manager."""
        await self.startup()
        try:
            yield self
        finally:
            await self.shutdown()

    # ── Accessors ──────────────────────────────────────────

    @property
    def db(self) -> DatabaseManager:
        if self._db is None:
            raise RuntimeError("Database not initialized")
        return self._db

    @property
    def event_bus(self) -> EventBus:
        if self._event_bus is None:
            raise RuntimeError("EventBus not initialized")
        return self._event_bus

    @property
    def job_manager(self) -> JobManager:
        if self._job_manager is None:
            raise RuntimeError("JobManager not initialized")
        return self._job_manager

    @property
    def agent_registry(self) -> AgentRegistry:
        if self._agent_registry is None:
            raise RuntimeError("AgentRegistry not initialized")
        return self._agent_registry

    @property
    def workflow_compiler(self) -> WorkflowCompiler:
        if self._workflow_compiler is None:
            raise RuntimeError("WorkflowCompiler not initialized")
        return self._workflow_compiler


# Global application instance (singleton)
_app_instance: Optional[Application] = None


def get_application() -> Application:
    """Return the global application singleton."""
    global _app_instance
    if _app_instance is None:
        _app_instance = Application()
    return _app_instance


def set_application(app: Application) -> None:
    """Set the global application singleton (for testing)."""
    global _app_instance
    _app_instance = app
