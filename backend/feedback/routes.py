"""Asset Feedback Loop API (Phase 13.4-C, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.feedback.service import FeedbackService

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

_service = FeedbackService()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


class EventBody(BaseModel):
    kind: str = "critic"
    target_type: str
    target_id: str
    source: str = ""
    project_id: str = ""
    severity: str = "medium"
    issues: list[str] = []
    metrics: dict = {}


class OutcomeBody(BaseModel):
    dna_id: str
    success: bool | None = None
    quality: float | None = None
    human_score: float | None = None
    source: str = "qc"


class CandidateBody(BaseModel):
    target_type: str
    target_id: str
    suggested_changes: dict
    reason: str = ""
    evidence: dict = {}
    project_id: str = ""


class ReviewBody(BaseModel):
    decision: str
    reviewer: str = "human"


@router.get("/stats")
def stats():
    return _service.stats()


@router.get("/events")
def list_events(target_type: str | None = None, target_id: str | None = None, kind: str | None = None):
    return {"events": _service.list_events(target_type=target_type, target_id=target_id, kind=kind)}


@router.post("/events")
def record_event(body: EventBody):
    try:
        return _service.record_event(**body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/shots/{dna_id}/outcomes")
def record_outcome(dna_id: str, body: OutcomeBody):
    try:
        return _service.record_shot_outcome(dna_id, success=body.success, quality=body.quality, human_score=body.human_score, source=body.source)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/shots/{dna_id}/stats")
def shot_stats(dna_id: str):
    return _service.shot_stats(dna_id)


@router.get("/candidates")
def list_candidates(status: str | None = None):
    return {"candidates": [c.to_dict() for c in _service.store.list_candidates(status=status)]}


@router.post("/candidates")
def propose_candidate(body: CandidateBody):
    try:
        return _service.propose_candidate(**body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/candidates/auto")
def auto_propose(min_samples: int = 10, prior_weight: int = 5):
    try:
        return {"candidates": _service.auto_propose(min_samples=min_samples, prior_weight=prior_weight)}
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


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