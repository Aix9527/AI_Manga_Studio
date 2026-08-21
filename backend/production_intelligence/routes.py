"""Production Intelligence API (Phase 13.5-B, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.production_intelligence.service import ProductionIntelligenceService

router = APIRouter(prefix="/api/production-intelligence", tags=["production-intelligence"])

_service = ProductionIntelligenceService()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


# ------------------------------------------------------------- stats / events
@router.get("/stats")
def stats():
    return _service.stats()


class EventBody(BaseModel):
    event_type: str
    project_id: str = ""
    episode_id: str = ""
    shot_id: str = ""
    actor: str = "pipeline"
    audit_id: str = ""
    payload: dict = {}


@router.post("/events")
def record_event(body: EventBody):
    try:
        return _service.record_event(**body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/events")
def list_events(event_type: str | None = None, project_id: str | None = None,
                episode_id: str | None = None, shot_id: str | None = None):
    return {"events": _service.list_events(event_type=event_type, project_id=project_id,
                                           episode_id=episode_id, shot_id=shot_id)}


# ------------------------------------------------------------- B2 analytics
@router.get("/analytics/cost")
def cost_intelligence(project_id: str | None = None):
    return _service.cost_intelligence(project_id=project_id)


@router.get("/analytics/cycle")
def cycle_intelligence(project_id: str | None = None):
    return _service.cycle_intelligence(project_id=project_id)


@router.get("/analytics/directors")
def director_intelligence(project_id: str | None = None):
    return {"directors": _service.director_intelligence(project_id=project_id)}


@router.get("/analytics/prompt-roi")
def prompt_roi(project_id: str | None = None):
    return {"prompts": _service.prompt_roi(project_id=project_id)}


# ------------------------------------------------------------- B3 center
@router.get("/overview")
def overview(project_id: str | None = None):
    return _service.overview(project_id=project_id)


@router.get("/episode-roi")
def episode_roi(project_id: str | None = None):
    return {"episodes": _service.episode_roi(project_id=project_id)}


@router.get("/risk-radar")
def risk_radar(project_id: str | None = None):
    return {"risks": _service.risk_radar(project_id=project_id)}


@router.get("/optimization-candidates")
def optimization_candidates(project_id: str | None = None):
    return {"suggestions": _service.optimization_candidates(project_id=project_id)}


# ------------------------------------------------------------- B4 candidates
@router.post("/candidates")
def propose_candidates(project_id: str | None = None):
    try:
        return {"candidates": _service.propose_candidates(project_id=project_id)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/candidates")
def list_candidates(status: str | None = None):
    return {"candidates": _service.list_candidates(status=status)}


class ReviewBody(BaseModel):
    decision: str
    reviewer: str = "human"


@router.post("/candidates/{candidate_id}/review")
def review_candidate(candidate_id: str, body: ReviewBody):
    try:
        return _service.review_candidate(candidate_id, body.decision, body.reviewer)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/candidates/{candidate_id}/apply")
def apply_candidate(candidate_id: str):
    try:
        return _service.apply_candidate(candidate_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)