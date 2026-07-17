"""
AI Manga Studio Pro V1.0 — Shot Management Routes

All shot I/O is driven by UnifiedShot JSON files on disk.
ComfyUI, Python, and Web all read/write the same JSON.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from backend.unified_shot import UnifiedShot, ShotStatus, Camera, Emotion

router = APIRouter(prefix="/api/shots", tags=["Shots"])


# ── helpers ────────────────────────────────────────────────

def _shot_json_path(project_id: str, chapter: int, shot_idx: int) -> str:
    from backend.config import get_config
    config = get_config()
    base = config.project.output_path or config.project.root_path
    return os.path.join(base, project_id, f"ch{chapter:02d}", "shots", f"shot_{shot_idx:03d}.json")


def _list_shots(project_id: str, chapter: int) -> List[UnifiedShot]:
    from backend.config import get_config
    config = get_config()
    base = config.project.output_path or config.project.root_path
    shot_dir = os.path.join(base, project_id, f"ch{chapter:02d}", "shots")
    if not os.path.isdir(shot_dir):
        return []
    shots = []
    for f in sorted(os.listdir(shot_dir)):
        if f.startswith("shot_") and f.endswith(".json") and "workflow" not in f:
            try:
                shots.append(UnifiedShot.from_json_file(os.path.join(shot_dir, f)))
            except Exception as e:
                logger.warning(f"Failed to load {f}: {e}")
    return shots


# ── req/res ─────────────────────────────────────────────────

class ShotUpdateRequest(BaseModel):
    status: Optional[str] = None
    camera: Optional[str] = None
    emotion: Optional[str] = None
    duration: Optional[float] = None
    dialogue: Optional[str] = None
    characters: Optional[List[str]] = None
    background: Optional[str] = None
    voice: Optional[str] = None


class ShotListResponse(BaseModel):
    total: int = 0
    shots: List[Dict] = []


# ── routes ──────────────────────────────────────────────────

@router.get("", response_model=ShotListResponse)
async def list_shots(
    project_id: str = Query(...),
    chapter: int = Query(1),
    status: Optional[str] = Query(None),
) -> ShotListResponse:
    shots = _list_shots(project_id, chapter)
    if status:
        shots = [s for s in shots if s.status.value == status]
    return ShotListResponse(
        total=len(shots),
        shots=[s.to_minimal_dict() for s in shots],
    )


@router.get("/detail")
async def get_shot(
    project_id: str = Query(...),
    chapter: int = Query(...),
    shot_idx: int = Query(...),
) -> Dict:
    path = _shot_json_path(project_id, chapter, shot_idx)
    if not os.path.exists(path):
        raise HTTPException(404, f"Shot not found: {path}")
    return UnifiedShot.from_json_file(path).model_dump(mode="json")


@router.patch("/detail")
async def update_shot(
    body: ShotUpdateRequest,
    project_id: str = Query(...),
    chapter: int = Query(...),
    shot_idx: int = Query(...),
) -> Dict:
    path = _shot_json_path(project_id, chapter, shot_idx)
    if not os.path.exists(path):
        raise HTTPException(404, f"Shot not found: {path}")

    shot = UnifiedShot.from_json_file(path)
    if body.status is not None:
        try: shot.status = ShotStatus(body.status)
        except ValueError: raise HTTPException(400, f"Invalid status: {body.status}")
    if body.camera is not None:
        try: shot.camera = Camera(body.camera)
        except ValueError: raise HTTPException(400, f"Invalid camera: {body.camera}")
    if body.emotion is not None:
        try: shot.emotion = Emotion(body.emotion)
        except ValueError: raise HTTPException(400, f"Invalid emotion: {body.emotion}")
    if body.duration is not None: shot.duration = body.duration
    if body.dialogue is not None: shot.dialogue = body.dialogue
    if body.characters is not None: shot.characters = body.characters
    if body.background is not None: shot.background = body.background
    if body.voice is not None: shot.voice = body.voice

    shot.to_json_file(path)
    logger.info(f"Shot updated: {path}")
    return shot.to_minimal_dict()


@router.post("/retry")
async def retry_shot(
    project_id: str = Query(...),
    chapter: int = Query(...),
    shot_idx: int = Query(...),
) -> Dict:
    path = _shot_json_path(project_id, chapter, shot_idx)
    if not os.path.exists(path):
        raise HTTPException(404, f"Shot not found: {path}")

    shot = UnifiedShot.from_json_file(path)
    if shot.retry_count >= shot.retry_max:
        raise HTTPException(400, f"Max retries ({shot.retry_max}) reached")
    shot.mark_generating()
    shot.to_json_file(path)
    return {"shot_idx": shot_idx, "status": "generating", "retry_count": shot.retry_count}


@router.delete("/detail")
async def delete_shot(
    project_id: str = Query(...),
    chapter: int = Query(...),
    shot_idx: int = Query(...),
) -> Dict:
    path = _shot_json_path(project_id, chapter, shot_idx)
    if not os.path.exists(path):
        raise HTTPException(404, f"Shot not found: {path}")

    shot = UnifiedShot.from_json_file(path)
    for mp in [shot.image_path, shot.video_path, shot.thumbnail_path]:
        if mp and os.path.exists(mp):
            os.remove(mp)
    os.remove(path)
    return {"status": "deleted", "shot_idx": shot_idx}
