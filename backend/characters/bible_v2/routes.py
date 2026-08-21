"""Character Bible v2 API (Phase 13.1, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.characters.bible_v2.service import CharacterBibleService

router = APIRouter(prefix="/api/characters/bible", tags=["character-bible"])

_service = CharacterBibleService()


class CreateBody(BaseModel):
    character_id: str
    name: str = ""
    age: int = 0
    gender: str = ""


class IdentityBody(BaseModel):
    name: str | None = None
    age: int | None = None
    gender: str | None = None
    personality: list[str] | None = None
    background: str | None = None
    voice: dict | None = None


class VersionBody(BaseModel):
    version_id: str
    parent: str = ""
    appearance: dict = {}
    clothing: dict = {}
    notes: str = ""
    approved: bool = False


class VersionStatusBody(BaseModel):
    approved: bool | None = None
    locked: bool | None = None


class AssetBody(BaseModel):
    key: str
    image_path: str = ""
    prompt: str = ""
    seed: int = 0
    description: str = ""


@router.post("")
def create(body: CreateBody):
    try:
        return _service.create(body.character_id, body.name, body.age, body.gender).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("")
def list_bibles():
    return {"bibles": [b.to_dict() for b in _service.list()]}


@router.get("/{character_id}")
def get_bible(character_id: str):
    bible = _service.get(character_id)
    if not bible:
        raise HTTPException(status_code=404, detail="bible not found")
    return bible.to_dict()


@router.patch("/{character_id}/identity")
def update_identity(character_id: str, body: IdentityBody):
    try:
        return _service.update_identity(character_id, **body.model_dump(exclude_none=True)).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{character_id}/completeness")
def completeness(character_id: str):
    try:
        return _service.completeness(character_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{character_id}/versions")
def add_version(character_id: str, body: VersionBody):
    try:
        return _service.add_version(
            character_id, body.version_id, body.parent, body.appearance,
            body.clothing, body.notes, body.approved,
        ).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{character_id}/versions/{version_id}/status")
def set_version_status(character_id: str, version_id: str, body: VersionStatusBody):
    try:
        return _service.set_version_status(character_id, version_id, approved=body.approved, locked=body.locked).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{character_id}/views")
def add_view(character_id: str, body: AssetBody):
    try:
        return _service.add_view(character_id, body.key, body.image_path, body.prompt, body.seed).to_dict()
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{character_id}/expressions")
def add_expression(character_id: str, body: AssetBody):
    try:
        return _service.add_expression(character_id, body.key, body.image_path, body.prompt, body.seed).to_dict()
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{character_id}/actions")
def add_action(character_id: str, body: AssetBody):
    try:
        return _service.add_action(character_id, body.key, body.description, body.prompt, body.image_path).to_dict()
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
