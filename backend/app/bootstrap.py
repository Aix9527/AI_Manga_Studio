"""Application bootstrap — creates and wires the FastAPI app."""

from fastapi import FastAPI

from backend.app.container import ApplicationContainer
from backend.app.container_builder import build_container
from backend.app.error_handlers import register_error_handlers
from backend.app.lifecycle import create_lifespan
from backend.app.middleware import register_middleware
from backend.app.routes import register_routes
from backend.modules.platform.infrastructure.settings import AppSettings


def create_application(
    settings: AppSettings | None = None,
) -> FastAPI:
    """Create a fully wired FastAPI application."""
    resolved_settings = settings or AppSettings()
    container: ApplicationContainer = build_container(resolved_settings)

    app = FastAPI(
        title="AI Manga Studio",
        version="0.1.0",
        lifespan=create_lifespan(container),
    )

    app.state.container = container

    register_middleware(app)
    register_error_handlers(app)
    register_routes(app, container)

    return app
