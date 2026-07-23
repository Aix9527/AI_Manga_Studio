"""Application bootstrap — creates and wires the FastAPI app."""

from fastapi import FastAPI

from backend.app.error_handlers import register_error_handlers
from backend.app.lifecycle import create_lifespan
from backend.app.middleware import register_middleware
from backend.app.routes import register_routes
from backend.modules.platform.infrastructure.database import DatabaseManager
from backend.modules.platform.infrastructure.settings import AppSettings


def create_application(
    settings: AppSettings | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Runtime dependencies are initialized inside the lifespan context so the
    module can be imported safely by Uvicorn, tests, and tooling.
    """
    resolved_settings = settings or AppSettings()
    database_manager = DatabaseManager(resolved_settings)

    app = FastAPI(
        title="AI Manga Studio",
        version="0.1.0",
        lifespan=create_lifespan(resolved_settings, database_manager),
    )

    register_middleware(app)
    register_error_handlers(app)
    register_routes(app)

    return app
