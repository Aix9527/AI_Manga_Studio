"""Prompt OS API (Phase 13.6, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.prompt_os.service import PromptOS

router = APIRouter(prefix="/api/prompt-os", tags=["prompt-os"])

_os = PromptOS()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


# ------------------------------------------------------------- stats
@router.get("/stats")
def stats():
    return _os.stats()


# ------------------------------------------------------------- engines
@router.get("/engines")
def list_engines():
    return {"engines": _os.engines()}


@router.post("/engines/{key}/run")
def run_engine(key: str, body: dict):
    try:
        return _os.run_engine(key, body)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- DNA
@router.get("/dna")
def list_dna(kind: str | None = None):
    if kind:
        return {"entries": _os.dna_by_kind(kind)}
    return {"entries": _os.dna_all()}


class DNABody(BaseModel):
    id: str = ""
    kind: str = "character"
    name: str = ""
    description: str = ""
    values: dict = {}
    tags: list[str] = []


@router.post("/dna")
def add_dna(body: DNABody):
    try:
        return _os.dna_add(body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- compiler
class CompileBody(BaseModel):
    logline: str
    shot_id: str = ""
    duration_seconds: float = 5.0
    camera_shot: str = ""
    lens: str = ""
    movement: str = ""
    lighting: str = ""
    composition: str = ""
    style: str = ""
    director_intent: str = ""


@router.post("/compile")
def compile_shot(body: CompileBody):
    try:
        return _os.compile_shot(body.logline, **body.model_dump(exclude={"logline"}))
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/compile/sequence")
def compile_sequence(body: list[str]):
    try:
        return {"shots": _os.compile_sequence(body)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- ShotDesign
@router.get("/shot-designs")
def list_shot_designs():
    return {"shots": _os.list_shot_designs()}


@router.get("/shot-designs/{design_id}")
def get_shot_design(design_id: str):
    try:
        design = _os.get_shot_design(design_id)
        if not design:
            raise KeyError(design_id)
        return design.to_dict()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


class StatusBody(BaseModel):
    status: str
    approved_by: str = "human"


@router.post("/shot-designs/{design_id}/status")
def set_status(design_id: str, body: StatusBody):
    try:
        return _os.set_status(design_id, body.status, body.approved_by)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


class NewVersionBody(BaseModel):
    overrides: dict = {}
    notes: str = ""


@router.post("/shot-designs/{design_id}/versions")
def new_version(design_id: str, body: NewVersionBody):
    try:
        return _os.new_version(design_id, overrides=body.overrides, notes=body.notes)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- evolution
class MetricBody(BaseModel):
    shot_design_id: str
    project_id: str = ""
    episode_id: str = ""
    completion_rate: float = 0.0
    like_rate: float = 0.0
    comment_rate: float = 0.0
    favorite_rate: float = 0.0
    views: int = 0


@router.post("/metrics")
def record_metric(body: MetricBody):
    try:
        return _os.record_metric(**body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/leaderboard")
def leaderboard(limit: int = 20):
    return {"leaderboard": _os.leaderboard(limit=limit)}


@router.post("/evolution/candidates")
def propose_candidates():
    try:
        return {"candidates": _os.propose_candidates()}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/evolution")
def evolution_records(status: str | None = None):
    return {"records": _os.evolution_records(status=status)}


class ReviewBody(BaseModel):
    decision: str
    reviewer: str = "human"


@router.post("/evolution/{record_id}/review")
def review_candidate(record_id: str, body: ReviewBody):
    try:
        return _os.review_candidate(record_id, body.decision, body.reviewer)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/evolution/{record_id}/apply")
def apply_candidate(record_id: str):
    try:
        return _os.apply_candidate(record_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)