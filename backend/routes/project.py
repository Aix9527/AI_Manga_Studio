"""
AI Manga Studio Pro V1.0 — Project Management Routes

Endpoints:
    GET  /api/projects        → List all projects
    POST /api/projects        → Create new project
    GET  /api/projects/{id}   → Get project details
    DELETE /api/projects/{id} → Delete project
    POST /api/projects/{id}/novel → Upload novel for project
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/projects", tags=["Projects"])

# In-memory project store (replace with DB in production)
_projects: Dict[str, Dict[str, Any]] = {}
PROJECTS_DIR = "D:/AI_Manga_Studio/project"


# --- Models ---

class ProjectCreate(BaseModel):
    """Request body for project creation."""
    name: str = Field(..., description="Project name", min_length=1, max_length=128)
    description: str = Field("", description="Project description")
    style: str = Field("anime", description="Art style: anime, manga, realistic")
    language: str = Field("zh", description="Source language")


class ProjectResponse(BaseModel):
    """Project response model."""
    id: str
    name: str
    description: str
    style: str
    language: str
    status: str
    created_at: str
    updated_at: str
    chapter_count: int = 0
    shot_count: int = 0


class ProjectListResponse(BaseModel):
    """Project list response."""
    total: int
    projects: List[ProjectResponse]


# --- Routes ---

@router.get("", response_model=ProjectListResponse)
async def list_projects() -> ProjectListResponse:
    """List all projects, sorted by last update."""
    projects_list = []
    for pid, pdata in sorted(
        _projects.items(),
        key=lambda x: x[1].get("updated_at", ""),
        reverse=True,
    ):
        projects_list.append(ProjectResponse(
            id=pid,
            name=pdata["name"],
            description=pdata.get("description", ""),
            style=pdata.get("style", "anime"),
            language=pdata.get("language", "zh"),
            status=pdata.get("status", "idle"),
            created_at=pdata.get("created_at", ""),
            updated_at=pdata.get("updated_at", ""),
            chapter_count=pdata.get("chapter_count", 0),
            shot_count=pdata.get("shot_count", 0),
        ))

    # Also scan project directory
    if os.path.isdir(PROJECTS_DIR):
        for entry in os.listdir(PROJECTS_DIR):
            entry_path = os.path.join(PROJECTS_DIR, entry)
            meta_path = os.path.join(entry_path, "meta.json")
            if os.path.isfile(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                if entry not in _projects:
                    projects_list.append(ProjectResponse(
                        id=entry,
                        name=meta.get("name", entry),
                        description=meta.get("description", ""),
                        style=meta.get("style", "anime"),
                        language=meta.get("language", "zh"),
                        status=meta.get("status", "idle"),
                        created_at=meta.get("created_at", ""),
                        updated_at=meta.get("updated_at", ""),
                        chapter_count=meta.get("chapter_count", 0),
                        shot_count=meta.get("shot_count", 0),
                    ))

    return ProjectListResponse(total=len(projects_list), projects=projects_list)


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(body: ProjectCreate) -> ProjectResponse:
    """Create a new project."""
    import uuid
    import time

    pid = str(uuid.uuid4())[:8]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    project_data = {
        "id": pid,
        "name": body.name,
        "description": body.description,
        "style": body.style,
        "language": body.language,
        "status": "idle",
        "created_at": now,
        "updated_at": now,
        "chapter_count": 0,
        "shot_count": 0,
    }
    _projects[pid] = project_data

    # Create project directory
    project_dir = os.path.join(PROJECTS_DIR, pid)
    os.makedirs(project_dir, exist_ok=True)

    meta_path = os.path.join(project_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(project_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Project created: {pid} ({body.name})")

    return ProjectResponse(**project_data)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str) -> ProjectResponse:
    """Get project details."""
    project = _projects.get(project_id)
    if not project:
        # Try loading from disk
        meta_path = os.path.join(PROJECTS_DIR, project_id, "meta.json")
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                project = json.load(f)
                _projects[project_id] = project

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse(
        id=project.get("id", project_id),
        name=project["name"],
        description=project.get("description", ""),
        style=project.get("style", "anime"),
        language=project.get("language", "zh"),
        status=project.get("status", "idle"),
        created_at=project.get("created_at", ""),
        updated_at=project.get("updated_at", ""),
        chapter_count=project.get("chapter_count", 0),
        shot_count=project.get("shot_count", 0),
    )


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> Dict[str, str]:
    """Delete a project and its files."""
    if project_id in _projects:
        del _projects[project_id]

    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if os.path.isdir(project_dir):
        import shutil
        shutil.rmtree(project_dir, ignore_errors=True)

    logger.info(f"Project deleted: {project_id}")
    return {"status": "deleted", "project_id": project_id}


@router.post("/{project_id}/novel")
async def upload_novel(
    project_id: str,
    file: UploadFile = File(...),
    title: str = Form(""),
) -> Dict[str, Any]:
    """Upload a novel text file for a project.

    Args:
        project_id: Project ID.
        file: Novel text file (.txt).
        title: Novel title.

    Returns:
        Upload status.
    """
    if project_id not in _projects:
        meta_path = os.path.join(PROJECTS_DIR, project_id, "meta.json")
        if not os.path.isfile(meta_path):
            raise HTTPException(status_code=404, detail="Project not found")

    project_dir = os.path.join(PROJECTS_DIR, project_id)
    novel_path = os.path.join(project_dir, "novel.txt")

    content = await file.read()
    text = content.decode("utf-8", errors="replace")

    # Save novel
    os.makedirs(project_dir, exist_ok=True)
    with open(novel_path, "w", encoding="utf-8") as f:
        f.write(text)

    # Update project metadata
    if project_id in _projects:
        _projects[project_id]["novel_title"] = title or file.filename
        _projects[project_id]["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logger.info(f"Novel uploaded for project {project_id}: {novel_path} ({len(text)} chars)")

    return {
        "status": "uploaded",
        "project_id": project_id,
        "file_size": len(text),
        "path": novel_path,
    }
