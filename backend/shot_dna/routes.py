"""Shot DNA API (Phase 13.1, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.shot_dna.library import ShotDNALibrary
from backend.shot_dna.retrieval import ShotDNARetriever

router = APIRouter(prefix="/api/shot-dna", tags=["shot-dna"])

_library = ShotDNALibrary()
_retriever = ShotDNARetriever(_library)


class AddBody(BaseModel):
    id: str = ""
    category: str
    scene: str = ""
    camera: dict = {}
    lens: str = ""
    lighting: str = ""
    composition: str = ""
    emotion: str = ""
    style: str = ""
    tags: list[str] = []
    prompt_template: str = ""
    success_rate: float = 0.8


class RetrieveBody(BaseModel):
    category: str = ""
    scene: str = ""
    emotion: str = ""
    camera_movement: str = ""
    lighting: str = ""
    top_k: int = 3


@router.get("")
def list_dna(category: str | None = None):
    items = _library.by_category(category) if category else _library.all()
    return {"items": [d.to_dict() for d in items]}


@router.get("/stats")
def stats():
    return _library.stats()


@router.get("/hit-rate")
def hit_rate():
    return _retriever.hit_rate()


@router.get("/{dna_id}")
def get_dna(dna_id: str):
    dna = _library.get(dna_id)
    if not dna:
        raise HTTPException(status_code=404, detail="shot dna not found")
    return dna.to_dict()


@router.post("")
def add_dna(body: AddBody):
    return _library.add_from_dict(body.model_dump(exclude_none=True)).to_dict()


@router.post("/retrieve")
def retrieve(body: RetrieveBody):
    return _retriever.retrieve_with_stats(**body.model_dump(exclude_none=True))


@router.post("/{dna_id}/use")
def register_use(dna_id: str, body: dict):
    if not _library.get(dna_id):
        raise HTTPException(status_code=404, detail="shot dna not found")
    _library.register_use(dna_id, success=body.get("success"))
    return {"ok": True, "dna_id": dna_id}
