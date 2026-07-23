"""
API Routes — REST + WebSocket endpoints (Part 14)

FastAPI-based API layer with:
- Project CRUD
- Character management
- Storyboard + Shot management
- Asset management
- Job submission and monitoring
- Provider health checks
- WebSocket for real-time job progress (SSE for streaming)

Routes:
- GET    /api/v1/projects
- POST   /api/v1/projects
- GET    /api/v1/projects/{project_id}
- DELETE /api/v1/projects/{project_id}
- GET    /api/v1/projects/{project_id}/characters
- POST   /api/v1/projects/{project_id}/characters
- GET    /api/v1/projects/{project_id}/storyboards
- POST   /api/v1/projects/{project_id}/storyboards
- POST   /api/v1/storyboards/{storyboard_id}/shots
- GET    /api/v1/projects/{project_id}/assets
- POST   /api/v1/jobs
- GET    /api/v1/jobs/{job_id}
- GET    /api/v1/jobs/{job_id}/stream (SSE)
- GET    /api/v1/providers/health
- WS     /ws/jobs/{job_id}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import (
    APIRouter,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Query,
    Path,
    Body,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.database import DatabaseManager
from backend.services import (
    ProjectService,
    CharacterService,
    StoryboardService,
    AssetService,
    JobService,
)
from backend.providers import ProviderRegistry


logger = logging.getLogger(__name__)

# ── Router Setup ────────────────────────────────────────────────────────

api_router = APIRouter(prefix="/api/v1")


# ── Dependency Injection ────────────────────────────────────────────────

# These would normally be resolved via FastAPI's Depends() system.
# For MVP, we use module-level initialization.

_db: Optional[DatabaseManager] = None
_provider_registry: Optional[ProviderRegistry] = None


def init_api(db: DatabaseManager, providers: ProviderRegistry) -> None:
    """Initialize API with real dependencies."""
    global _db, _provider_registry
    _db = db
    _provider_registry = providers


def _get_db() -> DatabaseManager:
    if _db is None:
        raise RuntimeError("API not initialized. Call init_api() first.")
    return _db


def _get_providers() -> ProviderRegistry:
    if _provider_registry is None:
        raise RuntimeError("API not initialized. Call init_api() first.")
    return _provider_registry


# ── Project Routes ──────────────────────────────────────────────────────


@api_router.get("/projects")
async def list_projects(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """List active projects."""
    service = ProjectService(_get_db())
    projects = await service.list_projects(offset=offset, limit=limit)
    return {"projects": projects, "count": len(projects)}


@api_router.post("/projects")
async def create_project(
    name: str = Body(..., min_length=1, max_length=255),
    description: str = Body(""),
    settings: dict[str, Any] = Body({}),
) -> dict[str, Any]:
    """Create a new project."""
    service = ProjectService(_get_db())
    project = await service.create_project(
        name=name, description=description, settings=settings
    )
    return {"project": project}


@api_router.get("/projects/{project_id}")
async def get_project(
    project_id: str = Path(..., min_length=1),
) -> dict[str, Any]:
    """Get a project by ID."""
    service = ProjectService(_get_db())
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project}


@api_router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str = Path(..., min_length=1),
) -> dict[str, Any]:
    """Soft-delete a project."""
    service = ProjectService(_get_db())
    success = await service.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted", "project_id": project_id}


# ── Character Routes ────────────────────────────────────────────────────


@api_router.get("/projects/{project_id}/characters")
async def list_characters(
    project_id: str = Path(..., min_length=1),
) -> dict[str, Any]:
    """List characters in a project."""
    service = CharacterService(_get_db())
    characters = await service.list_characters(project_id)
    return {"characters": characters, "count": len(characters)}


@api_router.post("/projects/{project_id}/characters")
async def create_character(
    project_id: str = Path(..., min_length=1),
    name: str = Body(..., min_length=1),
    role: str = Body("supporting"),
    appearance: str = Body(""),
    personality: str = Body(""),
) -> dict[str, Any]:
    """Create a character for a project."""
    service = CharacterService(_get_db())
    character = await service.create_character(
        project_id=project_id,
        name=name,
        role=role,
        appearance=appearance,
        personality=personality,
    )
    return {"character": character}


# ── Storyboard Routes ───────────────────────────────────────────────────


@api_router.get("/projects/{project_id}/storyboards")
async def list_storyboards(
    project_id: str = Path(..., min_length=1),
) -> dict[str, Any]:
    """List storyboards in a project."""
    service = StoryboardService(_get_db())
    storyboards = await service.list_storyboards(project_id)
    return {"storyboards": storyboards, "count": len(storyboards)}


@api_router.post("/projects/{project_id}/storyboards")
async def create_storyboard(
    project_id: str = Path(..., min_length=1),
    name: str = Body(""),
) -> dict[str, Any]:
    """Create a storyboard for a project."""
    service = StoryboardService(_get_db())
    storyboard = await service.create_storyboard(
        project_id=project_id, name=name
    )
    return {"storyboard": storyboard}


@api_router.get("/storyboards/{storyboard_id}/shots")
async def list_shots(
    storyboard_id: str = Path(..., min_length=1),
) -> dict[str, Any]:
    """List shots in a storyboard."""
    service = StoryboardService(_get_db())
    shots = await service.list_shots(storyboard_id)
    return {"shots": shots, "count": len(shots)}


@api_router.post("/storyboards/{storyboard_id}/shots")
async def create_shot(
    storyboard_id: str = Path(..., min_length=1),
    description: str = Body(""),
    shot_number: int = Body(1),
    camera_angle: str = Body(""),
) -> dict[str, Any]:
    """Add a shot to a storyboard."""
    service = StoryboardService(_get_db())
    shot = await service.add_shot(
        storyboard_id=storyboard_id,
        description=description,
        shot_number=shot_number,
        camera_angle=camera_angle,
    )
    return {"shot": shot}


# ── Asset Routes ────────────────────────────────────────────────────────


@api_router.get("/projects/{project_id}/assets")
async def list_assets(
    project_id: str = Path(..., min_length=1),
    asset_type: str = Query(""),
) -> dict[str, Any]:
    """List assets in a project."""
    service = AssetService(_get_db())
    assets = await service.list_assets(project_id, asset_type=asset_type)
    return {"assets": assets, "count": len(assets)}


@api_router.post("/projects/{project_id}/assets")
async def register_asset(
    project_id: str = Path(..., min_length=1),
    asset_type: str = Body(..., min_length=1),
    file_path: str = Body(""),
    file_name: str = Body(""),
    business_role: str = Body(""),
) -> dict[str, Any]:
    """Register a new asset."""
    service = AssetService(_get_db())
    asset = await service.create_asset(
        project_id=project_id,
        asset_type=asset_type,
        file_path=file_path,
        file_name=file_name,
        business_role=business_role,
    )
    return {"asset": asset}


# ── Job Routes ──────────────────────────────────────────────────────────


@api_router.post("/jobs")
async def submit_job(
    project_id: str = Body(..., min_length=1),
    job_type: str = Body(..., min_length=1),
    input_data: dict[str, Any] = Body({}),
    priority: int = Body(0),
) -> dict[str, Any]:
    """Submit a new job."""
    service = JobService(_get_db())
    job = await service.submit_job(
        project_id=project_id,
        job_type=job_type,
        input_data=input_data,
        priority=priority,
    )
    return {"job": job}


@api_router.get("/jobs/{job_id}")
async def get_job(
    job_id: str = Path(..., min_length=1),
) -> dict[str, Any]:
    """Get a job's current status."""
    service = JobService(_get_db())
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}


@api_router.get("/jobs/{job_id}/stream")
async def stream_job_progress(
    job_id: str = Path(..., min_length=1),
) -> StreamingResponse:
    """Stream job progress via Server-Sent Events."""
    service = JobService(_get_db())

    async def event_generator():
        last_status = ""
        for _ in range(300):  # Max 300s polling
            job = await service.get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            status = job["status"]
            if status != last_status:
                yield (
                    f"data: {json.dumps({'status': status, 'progress': job['progress']})}\n\n"
                )
                last_status = status

            if status in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Provider Routes ─────────────────────────────────────────────────────


@api_router.get("/providers/health")
async def providers_health() -> dict[str, Any]:
    """Check health of all registered providers."""
    registry = _get_providers()
    health = await registry.health_check_all()
    return {"providers": health}


# ── WebSocket Route ─────────────────────────────────────────────────────


@api_router.websocket("/ws/jobs/{job_id}")
async def websocket_job_progress(websocket: WebSocket, job_id: str) -> None:
    """WebSocket for real-time job progress updates."""
    await websocket.accept()
    service = JobService(_get_db())

    try:
        last_status = ""
        while True:
            job = await service.get_job(job_id)
            if not job:
                await websocket.send_json({"error": "Job not found"})
                break

            status = job["status"]
            if status != last_status:
                await websocket.send_json(
                    {
                        "status": status,
                        "progress": job["progress"],
                        "output_data": job.get("output_data", {}),
                    }
                )
                last_status = status

            if status in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}")


# ── App Factory ─────────────────────────────────────────────────────────


def create_app(db: DatabaseManager, providers: ProviderRegistry) -> FastAPI:
    """Create and configure the FastAPI application."""
    init_api(db, providers)

    app = FastAPI(
        title="AI Manga Studio API",
        version="1.0.0",
        description="REST + WebSocket API for AI Manga Studio",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(api_router)

    return app
