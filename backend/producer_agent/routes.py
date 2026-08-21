"""AI Producer Agent API (Phase 14.4, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.producer_agent.service import ProducerAgentService

router = APIRouter(prefix="/api/producer-agent", tags=["producer-agent"])

_service = ProducerAgentService()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


@router.get("/plan")
def plan(project_id: str | None = None):
    return _service.plan(project_id=project_id)


@router.get("/resource-suggestion")
def resource_suggestion():
    return _service.resource_suggestion()


@router.get("/risk/{candidate_id}/explain")
def explain_risk(candidate_id: str):
    try:
        return _service.explain_risk(candidate_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/report")
def report(project_id: str | None = None):
    return _service.report(project_id=project_id)
