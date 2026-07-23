
"""Route registration for all modules."""

from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    """Register all module API routes with the FastAPI application."""

    from backend.modules.platform.api.routes import router as platform_router
    from backend.modules.projects.api.routes import router as projects_router
    from backend.modules.narrative.api.routes import router as narrative_router
    from backend.modules.characters.api.routes import router as characters_router
    from backend.modules.storyboard.api.routes import router as storyboard_router
    from backend.modules.media.api.routes import router as media_router
    from backend.modules.generation.api.routes import router as generation_router
    from backend.modules.workflows.api.routes import router as workflows_router
    from backend.modules.characters.api.consistency_routes import consistency_router

    app.include_router(consistency_router, prefix="/api/v1", tags=["Character-Consistency"])
    app.include_router(platform_router, prefix="/api/v1", tags=["Platform"])
    app.include_router(projects_router, prefix="/api/v1", tags=["Projects"])
    app.include_router(narrative_router, prefix="/api/v1", tags=["Narrative"])
    app.include_router(characters_router, prefix="/api/v1", tags=["Characters"])
    app.include_router(storyboard_router, prefix="/api/v1", tags=["Storyboard"])
    app.include_router(media_router, prefix="/api/v1", tags=["Media"])
    app.include_router(generation_router, prefix="/api/v1", tags=["Generation"])
    app.include_router(workflows_router, prefix="/api/v1", tags=["Workflows"])
