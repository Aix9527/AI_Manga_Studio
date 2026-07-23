
"""Storyboard API routes."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from typing import Optional

from backend.app.container import ApplicationContainer
from backend.modules.storyboard.domain.storyboard import Shot, ShotCharacterBinding, StoryboardScene

router = APIRouter()


class CreateSceneRequest(BaseModel):
    project_id: str
    sequence_number: int
    title: str = ""
    description: str = ""
    narrative_scene_id: Optional[str] = None


class CreateShotRequest(BaseModel):
    scene_id: str
    project_id: str
    shot_number: int
    description: str = ""
    framing: str = ""
    camera_angle: str = ""


class BindCharacterRequest(BaseModel):
    shot_id: str
    character_id: str
    pose: str = ""
    expression: str = ""


@router.post("/storyboard/scenes")
async def create_scene(request: Request, body: CreateSceneRequest):
    container: ApplicationContainer = request.app.state.container
    scene = await container.storyboard.create_scene(body.project_id, body.sequence_number, body.title, body.description, body.narrative_scene_id)
    return {"sceneId": scene.scene_id, "projectId": scene.project_id, "sequenceNumber": scene.sequence_number, "title": scene.title}


@router.get("/storyboard/projects/{project_id}/scenes")
async def list_scenes(project_id: str, request: Request):
    container: ApplicationContainer = request.app.state.container
    scenes = await container.storyboard._storyboard_repo.list_scenes_by_project(project_id)
    return [{"sceneId": s.scene_id, "sequenceNumber": s.sequence_number, "title": s.title, "description": s.description} for s in scenes]


@router.post("/storyboard/shots")
async def create_shot(request: Request, body: CreateShotRequest):
    container: ApplicationContainer = request.app.state.container
    shot = await container.storyboard.create_shot(body.scene_id, body.project_id, body.shot_number, body.description, body.framing, body.camera_angle)
    return {"shotId": shot.shot_id, "sceneId": shot.scene_id, "shotNumber": shot.shot_number, "description": shot.description}


@router.get("/storyboard/scenes/{scene_id}/shots")
async def list_shots(scene_id: str, request: Request):
    container: ApplicationContainer = request.app.state.container
    shots = await container.storyboard._storyboard_repo.list_shots_by_scene(scene_id)
    return [{"shotId": s.shot_id, "shotNumber": s.shot_number, "description": s.description, "framing": s.framing} for s in shots]


@router.post("/storyboard/shots/characters")
async def bind_character(request: Request, body: BindCharacterRequest):
    container: ApplicationContainer = request.app.state.container
    await container.storyboard._storyboard_repo.bind_character(
        ShotCharacterBinding(shot_id=body.shot_id, character_id=body.character_id, pose=body.pose, expression=body.expression)
    )
    return {"status": "bound"}
