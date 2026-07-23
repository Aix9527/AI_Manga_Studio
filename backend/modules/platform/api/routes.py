"""Platform API routes."""

from fastapi import APIRouter, Request

from backend.app.container import ApplicationContainer

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    """Liveness and readiness check."""
    container: ApplicationContainer = request.app.state.container
    return await container.platform.health()
