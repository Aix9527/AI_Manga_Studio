"""World API (Phase 13.1, GPT spec): World Bible / Scene Bible / Locations / Environment Memory."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.world.service import WorldService

router = APIRouter(prefix="/api/world", tags=["world"])

_service = WorldService()


class WorldBody(BaseModel):
    project_id: str
    name: str = ""
    era: str = ""
    technology: str = ""
    civilization: str = ""
    power_system: str = ""
    physics_rules: list[str] = []
    visual_style: str = ""
    color_language: str = ""
    description: str = ""


class SceneBody(BaseModel):
    project_id: str
    world_id: str = ""
    name: str = ""
    location: str = ""
    time: str = ""
    weather: str = ""
    architecture: str = ""
    camera_rules: list[str] = []
    lighting_rules: list[str] = []
    forbidden_elements: list[str] = []
    environment_prompt: str = ""
    reference_image: str = ""


class LocationBody(BaseModel):
    project_id: str
    world_id: str = ""
    name: str = ""
    description: str = ""
    geography: str = ""
    architecture: str = ""
    landmarks: list[str] = []
    connected_to: list[str] = []


class NoteBody(BaseModel):
    project_id: str
    kind: str = "constraint"
    content: str
    source: str = "world_agent"


class PatchBody(BaseModel):
    pass  # accepts any JSON fields


@router.post("/worlds")
def create_world(body: WorldBody):
    return _service.create_world(**body.model_dump()).to_dict()


@router.get("/worlds")
def list_worlds(project_id: str | None = None):
    return {"worlds": [w.to_dict() for w in _service.list_worlds(project_id)]}


@router.get("/worlds/{world_id}")
def get_world(world_id: str):
    world = _service.get_world(world_id)
    if not world:
        raise HTTPException(status_code=404, detail="world not found")
    return world.to_dict()


@router.patch("/worlds/{world_id}")
def update_world(world_id: str, body: dict):
    try:
        return _service.update_world(world_id, **body).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/scenes")
def create_scene(body: SceneBody):
    return _service.create_scene(**body.model_dump()).to_dict()


@router.get("/scenes")
def list_scenes(project_id: str | None = None):
    return {"scenes": [s.to_dict() for s in _service.list_scenes(project_id)]}


@router.get("/scenes/{scene_id}")
def get_scene(scene_id: str):
    scene = _service.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="scene not found")
    return scene.to_dict()


@router.patch("/scenes/{scene_id}")
def update_scene(scene_id: str, body: dict):
    try:
        return _service.update_scene(scene_id, **body).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/locations")
def create_location(body: LocationBody):
    return _service.create_location(**body.model_dump()).to_dict()


@router.get("/locations")
def list_locations(project_id: str | None = None):
    return {"locations": [loc.to_dict() for loc in _service.list_locations(project_id)]}


@router.get("/locations/{location_id}")
def get_location(location_id: str):
    location = _service.get_location(location_id)
    if not location:
        raise HTTPException(status_code=404, detail="location not found")
    return location.to_dict()


@router.post("/environment/notes")
def note_environment(body: NoteBody):
    return _service.note_environment(body.project_id, body.kind, body.content, body.source)


@router.get("/environment/{project_id}")
def environment_summary(project_id: str):
    return _service.environment_summary(project_id)
