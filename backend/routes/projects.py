from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from backend.migration.scanner import ProjectScanner
from backend.migration.importer import AssetImporter

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def list_projects():
    scanner = ProjectScanner("projects")
    projects = scanner.scan()
    return {
        "projects": [
            {
                "name": p.name,
                "source_path": p.source_path,
                "file_count": p.file_count,
                "total_size": p.total_size,
                "has_outputs": p.has_outputs,
                "last_modified": p.last_modified,
            }
            for p in projects
        ]
    }


@router.get("/{project_id}/outputs/{path:path}")
async def serve_output(project_id: str, path: str):
    full_path = Path("projects") / project_id / "outputs" / path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)
