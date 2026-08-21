"""Multi-Project Production Orchestrator API (Phase 13.5-A, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.multi_project.service import MultiProjectOrchestrator

router = APIRouter(prefix="/api/production-orchestrator", tags=["production-orchestrator"])

_orchestrator = MultiProjectOrchestrator()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


# ------------------------------------------------------------- seasons
class SeasonBody(BaseModel):
    project_id: str
    season_no: int = 1
    name: str = ""
    target_episodes: int = 0


class SeasonStatusBody(BaseModel):
    status: str


@router.get("/seasons")
def list_seasons(project_id: str | None = None):
    return {"seasons": [s.to_dict() for s in _orchestrator.seasons.list(project_id)]}


@router.post("/seasons")
def create_season(body: SeasonBody):
    return _orchestrator.seasons.create_season(**body.model_dump()).to_dict()


@router.post("/seasons/{season_id}/episodes/{episode_id}")
def attach_episode(season_id: str, episode_id: str):
    try:
        return _orchestrator.seasons.attach_episode(season_id, episode_id).to_dict()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/seasons/{season_id}/status")
def set_season_status(season_id: str, body: SeasonStatusBody):
    try:
        return _orchestrator.seasons.set_status(season_id, body.status).to_dict()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/seasons/stats")
def season_stats(project_id: str | None = None):
    return _orchestrator.seasons.stats(project_id)


# ------------------------------------------------------------- resources
class ResourceBody(BaseModel):
    project_id: str
    season_id: str = ""
    gpu_capacity: int = 1
    budget_allocated: float = 0.0
    deadline: str = ""
    priority: int = 3


@router.get("/resources")
def list_resources(project_id: str | None = None):
    return {"resources": [r.to_dict() for r in _orchestrator.resources.list(project_id)]}


@router.post("/resources")
def plan_resource(body: ResourceBody):
    try:
        return _orchestrator.resources.plan(**body.model_dump()).to_dict()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/resources/stats")
def resource_stats():
    return _orchestrator.resources.stats()


# ------------------------------------------------------------- gpu queue
class GpuRecommendBody(BaseModel):
    limit: int = 10
    gpu_capacity: int = 1


@router.post("/gpu-queue/recommend")
def gpu_recommend(body: GpuRecommendBody):
    return _orchestrator.gpu_queue.recommend(limit=body.limit, gpu_capacity=body.gpu_capacity)


# ------------------------------------------------------------- budget
class PolicyBody(BaseModel):
    project_id: str
    monthly_limit: float
    episode_limit: float = 0.0
    warning_threshold: float = 0.8
    hard_limit: float = 1.0
    override_requires_approval: bool = True


class CostBody(BaseModel):
    amount: float
    source: str = "cost_meter"
    note: str = ""


@router.get("/budgets/{project_id}")
def budget_summary(project_id: str):
    return _orchestrator.budget.summary(project_id)


@router.post("/budgets/{project_id}/policy")
def set_budget_policy(project_id: str, body: PolicyBody):
    try:
        return _orchestrator.budget.set_policy(project_id, body.monthly_limit, body.episode_limit, body.warning_threshold, body.hard_limit, body.override_requires_approval).to_dict()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/budgets/{project_id}/cost")
def record_budget_cost(project_id: str, body: CostBody):
    return _orchestrator.budget.record_cost(project_id, body.amount, body.source, body.note)


@router.post("/budgets/{project_id}/authorize")
def authorize_budget(project_id: str, body: CostBody):
    return _orchestrator.budget.authorize(project_id, body.amount)


@router.post("/budgets/{project_id}/override")
def approve_override(project_id: str, body: dict):
    try:
        return _orchestrator.budget.approve_override(project_id, body.get("reviewer", "producer"))
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- scheduler
class DependencyBody(BaseModel):
    episode_id: str
    requires: list[str] = []
    previous_episode_asset: str = ""


class PlanBody(BaseModel):
    project_id: str
    max_parallel: int = 2


@router.post("/schedules/dependencies")
def register_dependency(body: DependencyBody):
    return _orchestrator.scheduler.register_dependency(**body.model_dump())


@router.post("/schedules/build")
def build_plan(body: PlanBody):
    try:
        return _orchestrator.scheduler.build_plan(body.project_id, body.max_parallel)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/schedules")
def list_plans(project_id: str | None = None):
    return {"plans": _orchestrator.scheduler.list_plans(project_id)}


@router.post("/schedules/{plan_id}/approve")
def approve_plan(plan_id: str, body: dict):
    try:
        return _orchestrator.scheduler.approve_plan(plan_id, body.get("reviewer", "producer"))
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/schedules/{plan_id}/dispatch")
def dispatch_plan(plan_id: str):
    try:
        return _orchestrator.scheduler.dispatch_plan(plan_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


# ------------------------------------------------------------- audit
@router.get("/audit")
def audit(limit: int = 100):
    return {"audit": _orchestrator.audit(limit)}