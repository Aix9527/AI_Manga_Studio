"""Episode API (Phase 13.1, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.production.readiness import AssetReadinessGate
from backend.story.episode.service import EpisodeService

router = APIRouter(prefix="/api/episodes", tags=["episodes"])

_service = EpisodeService(readiness_gate=AssetReadinessGate())


class CreateBody(BaseModel):
    project_id: str
    episode_no: int = 1
    season: int = 1
    title: str = ""
    operator: str = "dashboard"


class PlanBody(BaseModel):
    title: str | None = None
    hook: str | None = None
    conflict: str | None = None
    climax: str | None = None
    ending: str | None = None
    retention_strategy: str | None = None
    script_version: str | None = None
    operator: str = "dashboard"


class TransitionBody(BaseModel):
    to_status: str
    operator: str = "dashboard"


class RollbackBody(BaseModel):
    operator: str = "dashboard"


@router.get("/readiness/{project_id}")
def readiness(project_id: str):
    """Phase 13.3: production readiness gate report for a project."""
    return AssetReadinessGate().check_project(project_id)


@router.post("")
def create(body: CreateBody):
    try:
        episode = _service.create(
            body.project_id, body.episode_no, body.season, body.title, body.operator
        )
        return episode.to_dict()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_episodes(project_id: str | None = None):
    if project_id:
        return {"episodes": [e.to_dict() for e in _service.list_by_project(project_id)]}
    return {"episodes": [e.to_dict() for e in _service.repo.list_all()]}


@router.get("/summary")
def summary(project_id: str):
    return _service.summary(project_id)


@router.get("/{episode_id}")
def get_episode(episode_id: str):
    episode = _service.get(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="episode not found")
    return episode.to_dict()


@router.patch("/{episode_id}")
def update_plan(episode_id: str, body: PlanBody):
    try:
        episode = _service.update_plan(
            episode_id,
            title=body.title,
            hook=body.hook,
            conflict=body.conflict,
            climax=body.climax,
            ending=body.ending,
            retention_strategy=body.retention_strategy,
            script_version=body.script_version,
            operator=body.operator,
        )
        return episode.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{episode_id}/transition")
def transition(episode_id: str, body: TransitionBody):
    try:
        episode = _service.transition(episode_id, body.to_status, body.operator)
        return episode.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{episode_id}/rollback")
def rollback(episode_id: str, body: RollbackBody):
    try:
        episode = _service.rollback(episode_id, body.operator)
        return episode.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{episode_id}/audit")
def audit(episode_id: str):
    if not _service.get(episode_id):
        raise HTTPException(status_code=404, detail="episode not found")
    return {"entries": _service.audit(episode_id)}
