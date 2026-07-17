"""
AI Manga Studio Pro V1.0 — Generation Management Routes

Endpoints:
    POST /api/generation/start    → Start generation for a project
    POST /api/generation/stop     → Stop current generation
    GET  /api/generation/status   → Get generation status
    GET  /api/generation/logs     → Get generation logs (SSE)
    POST /api/generation/shot/{id}/retry → Retry a failed shot
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/generation", tags=["Generation"])

# In-memory generation state
_generation_state: Dict[str, Dict[str, Any]] = {}


# --- Models ---

class GenerationStartRequest(BaseModel):
    """Request to start generation."""
    project_id: str = Field(..., description="Project ID")
    workflow: str = Field("full", description="Workflow type: full, compose_only, video_only")
    options: Dict[str, Any] = Field(default_factory=dict, description="Generation options")


class GenerationStatus(BaseModel):
    """Current generation status."""
    project_id: str
    status: str  # idle, running, paused, completed, failed
    progress_pct: float = 0.0
    current_chapter: int = 0
    total_chapters: int = 0
    current_shot: int = 0
    total_shots: int = 0
    completed_shots: int = 0
    failed_shots: int = 0
    started_at: str = ""
    estimated_remaining: float = 0.0
    message: str = ""


class GenerationLog(BaseModel):
    """A single generation log entry."""
    timestamp: str
    level: str  # info, warning, error
    message: str
    chapter: int = 0
    shot: int = 0


# --- Routes ---

@router.post("/start", response_model=GenerationStatus)
async def start_generation(body: GenerationStartRequest) -> GenerationStatus:
    """Start the manga generation pipeline for a project.

    This kicks off the full pipeline: parse → characters →
    scenes → compose → video → lipsync → quality → merge.
    """
    pid = body.project_id

    # Check if already running
    if pid in _generation_state and _generation_state[pid].get("status") == "running":
        raise HTTPException(status_code=409, detail="Generation already in progress")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    state = {
        "project_id": pid,
        "status": "running",
        "progress_pct": 0.0,
        "current_chapter": 0,
        "total_chapters": 10,  # Will be updated after parsing
        "current_shot": 0,
        "total_shots": 0,
        "completed_shots": 0,
        "failed_shots": 0,
        "started_at": now,
        "estimated_remaining": 0.0,
        "message": "Initializing pipeline...",
        "logs": [],
    }

    _generation_state[pid] = state

    logger.info(f"Generation started for project {pid}")

    # In production, this would spawn the Scheduler in a background task
    # For now, simulate with placeholder progress

    return GenerationStatus(**state)


@router.post("/stop")
async def stop_generation(project_id: str = Query(...)) -> Dict[str, str]:
    """Stop a running generation."""
    if project_id not in _generation_state:
        raise HTTPException(status_code=404, detail="No active generation")

    state = _generation_state[project_id]
    state["status"] = "stopped"
    state["message"] = "Stopped by user"

    logger.info(f"Generation stopped for project {project_id}")
    return {"status": "stopped", "project_id": project_id}


@router.get("/status", response_model=GenerationStatus)
async def get_status(project_id: str = Query(...)) -> GenerationStatus:
    """Get current generation status."""
    state = _generation_state.get(project_id)
    if not state:
        return GenerationStatus(
            project_id=project_id,
            status="idle",
            message="No active generation",
        )
    return GenerationStatus(**state)


@router.get("/logs")
async def get_logs(
    project_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
) -> List[GenerationLog]:
    """Get recent generation log entries."""
    state = _generation_state.get(project_id)
    if not state:
        return []

    logs = state.get("logs", [])
    return [GenerationLog(**log) for log in logs[-limit:]]


@router.get("/logs/stream")
async def stream_logs(project_id: str = Query(...)):
    """Stream generation logs via Server-Sent Events (SSE)."""
    async def event_generator():
        last_index = 0
        while True:
            state = _generation_state.get(project_id, {})
            logs = state.get("logs", [])

            # Send new logs since last_index
            for i in range(last_index, len(logs)):
                yield f"data: {json.dumps(logs[i])}\n\n"

            last_index = len(logs)

            # If generation is done, close stream
            if state.get("status") in ("completed", "failed", "stopped", "idle"):
                yield f"data: {json.dumps({'status': state['status'], 'message': 'done'})}\n\n"
                break

            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/shot/{shot_id}/retry")
async def retry_shot(
    shot_id: str,
    project_id: str = Query(...),
    options: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Retry a specific failed shot.

    Args:
        shot_id: Shot identifier.
        project_id: Project ID.
        options: Optional override parameters.

    Returns:
        Retry status.
    """
    state = _generation_state.get(project_id)
    if not state:
        raise HTTPException(status_code=404, detail="Project not found")

    logger.info(f"Retrying shot {shot_id} for project {project_id}")

    # In production, this would re-submit the shot to the Scheduler
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "level": "info",
        "message": f"Shot {shot_id} retry initiated",
        "chapter": 0,
        "shot": int(shot_id) if shot_id.isdigit() else 0,
    }
    state.setdefault("logs", []).append(log_entry)

    return {
        "status": "retrying",
        "shot_id": shot_id,
        "project_id": project_id,
    }


# --- Internal helpers (used by Scheduler) ---

def update_generation_progress(
    project_id: str,
    current_chapter: int = 0,
    total_chapters: int = 0,
    current_shot: int = 0,
    total_shots: int = 0,
    completed_shots: int = 0,
    failed_shots: int = 0,
    message: str = "",
    level: str = "info",
) -> None:
    """Update generation progress (called by Scheduler).

    Args:
        project_id: Project ID.
        current_chapter: Current chapter index.
        total_chapters: Total chapters.
        current_shot: Current shot index.
        total_shots: Total shots in current chapter.
        completed_shots: Shots completed.
        failed_shots: Shots failed.
        message: Status message.
        level: Log level.
    """
    state = _generation_state.get(project_id)
    if not state:
        return

    state["current_chapter"] = current_chapter
    state["total_chapters"] = total_chapters
    state["current_shot"] = current_shot
    state["total_shots"] = total_shots
    state["completed_shots"] = completed_shots
    state["failed_shots"] = failed_shots
    state["message"] = message

    # Calculate progress
    if total_chapters > 0:
        chapter_progress = current_chapter / total_chapters
    else:
        chapter_progress = 0.0
    state["progress_pct"] = round(chapter_progress * 100, 1)

    if message:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
            "chapter": current_chapter,
            "shot": current_shot,
        }
        state.setdefault("logs", []).append(log_entry)


def set_generation_complete(project_id: str, success: bool = True, message: str = "") -> None:
    """Mark generation as complete.

    Args:
        project_id: Project ID.
        success: Whether generation succeeded.
        message: Completion message.
    """
    state = _generation_state.get(project_id)
    if not state:
        return

    state["status"] = "completed" if success else "failed"
    state["progress_pct"] = 100.0 if success else state.get("progress_pct", 0)
    state["message"] = message or ("Generation complete" if success else "Generation failed")

    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "level": "info" if success else "error",
        "message": state["message"],
        "chapter": 0,
        "shot": 0,
    }
    state.setdefault("logs", []).append(log_entry)
