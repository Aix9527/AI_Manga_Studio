
"""Media API routes."""

from fastapi import APIRouter, Request

from backend.app.container import ApplicationContainer

router = APIRouter()


@router.get("/media/projects/{project_id}/assets")
async def list_assets(project_id: str, request: Request):
    container: ApplicationContainer = request.app.state.container
    assets = await container.media._asset_repo.list_by_project(project_id)
    return [{"assetId": a.asset_id, "name": a.name, "mimeType": a.mime_type, "fileSize": a.file_size, "createdAt": a.created_at.isoformat()} for a in assets]
