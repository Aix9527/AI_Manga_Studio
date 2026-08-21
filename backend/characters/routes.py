"""Character API routes for FastAPI."""

import mimetypes

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.characters.service import CharacterService

router = APIRouter(prefix="/api/characters", tags=["Characters"])
service = CharacterService()


# ── Schemas ──

class CharacterImportRequest(BaseModel):
    name: str
    gender: str = ""
    age: int = 0
    species: str = "human"
    role: str = ""
    archetype: str = ""
    aliases: list[str] = []
    backstory: str = ""
    goal: str = ""
    arc_description: str = ""
    novel_id: str = ""
    appearance: dict = {}
    personality: dict = {}
    combat_style: dict = {}


class TraitRequest(BaseModel):
    character_id: str
    trait_type: str
    name: str
    value: str
    intensity: float = 1.0
    source_chapter: int = 0


class RelationshipRequest(BaseModel):
    character_id: str
    related_id: str
    relation_type: str
    description: str = ""
    intensity: float = 1.0


class ExtractRequest(BaseModel):
    text: str
    novel_id: str = ""


# ── Routes ──

@router.get("/")
def list_characters(novel_id: str = "", status: str = ""):
    return service.list_all(novel_id=novel_id)


@router.get("/search")
def search_characters(q: str = Query("", alias="q")):
    return service.search(q)


@router.get("/media/{image_id}")
def get_image_content(image_id: str):
    """Serve only image files referenced by an existing repository record."""
    try:
        image_path = service.resolve_image_path(image_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="未找到角色图片")
    except PermissionError:
        raise HTTPException(status_code=403, detail="图片路径不在允许目录内")
    except ValueError:
        raise HTTPException(status_code=415, detail="不支持的图片类型")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="图片文件不存在")
    media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    return FileResponse(image_path, media_type=media_type)


@router.get("/{character_id}")
def get_character(character_id: str):
    profile = service.get_profile(character_id)
    if not profile.get("character"):
        raise HTTPException(status_code=404, detail="Character not found")
    return profile


@router.post("/")
def create_character(req: CharacterImportRequest):
    return service.import_character(req.model_dump())


@router.post("/extract")
def extract_characters(req: ExtractRequest):
    chars = service.extract_from_text(req.text, req.novel_id)
    return {"count": len(chars), "characters": [c.to_dict() for c in chars]}


@router.delete("/{character_id}")
def delete_character(character_id: str):
    ok = service.delete(character_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"status": "deleted"}


@router.get("/{character_id}/images")
def list_images(character_id: str):
    return service.memory.get_images(character_id)


@router.post("/images")
def add_image(character_id: str, image_path: str, image_type: str = "reference", is_primary: bool = False, prompt: str = ""):
    return service.add_image(character_id, image_path, image_type, is_primary, prompt)


@router.get("/{character_id}/traits")
def list_traits(character_id: str):
    return service.memory.get_traits(character_id)


@router.post("/traits")
def add_trait(req: TraitRequest):
    from backend.characters.models import CharacterTrait
    t = CharacterTrait(**req.model_dump())
    service.memory.add_trait(t)
    return t


@router.get("/{character_id}/relationships")
def list_relationships(character_id: str):
    return service.memory.get_relationships(character_id)


@router.post("/relationships")
def add_relationship(req: RelationshipRequest):
    return service.add_relationship(req.character_id, req.related_id, req.relation_type, req.description)


@router.get("/{character_id}/graph")
def relationship_graph(character_id: str, depth: int = 2):
    return service.memory.get_relationship_graph(character_id, depth)


@router.get("/{character_id}/consistency")
def check_consistency(character_id: str, image_path: str):
    result = service.check_consistency(character_id, image_path)
    return {
        "character_id": character_id,
        "consistent": bool(result.get("consistent", False)),
        "score": float(result.get("score", 0.0)),
        "threshold": float(result.get("threshold", service.consistency.threshold)),
        **({"reason": result["reason"]} if "reason" in result else {}),
    }


@router.get("/{character_id}/costumes")
def list_costumes(character_id: str):
    return service.memory.get_costumes(character_id)
