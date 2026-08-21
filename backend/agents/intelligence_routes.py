"""Story Intelligence API (Phase 13.2, GPT spec).

- POST /api/intelligence/executive-producer   novel → season plan
- POST /api/intelligence/episode-planner      consume Episode layer
- POST /api/intelligence/world-analyzer       novel → World Bible
- POST /api/intelligence/retention/score      episode → retention metrics
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.episode_planner import EpisodePlannerAgent
from backend.agents.executive_producer import ExecutiveProducerAgent
from backend.agents.retention import RetentionIntelligenceEngine
from backend.agents.world_analyzer import WorldAnalyzerAgent

router = APIRouter(prefix="/api/intelligence", tags=["story-intelligence"])

_producer = ExecutiveProducerAgent()
_planner = EpisodePlannerAgent()
_world = WorldAnalyzerAgent()
_retention = RetentionIntelligenceEngine()


class ProducerBody(BaseModel):
    novel_text: str
    project_id: str
    platform: str = "douyin"
    budget: float = 0.0
    target_episodes: int = 100
    target_duration: float = 90.0
    season: int = 1
    write_episodes: bool = True


class PlannerBody(BaseModel):
    project_id: str
    operator: str = "episode_planner"


class SinglePlannerBody(BaseModel):
    episode_id: str
    novel_segment: str = ""
    operator: str = "episode_planner"


class WorldBody(BaseModel):
    project_id: str
    novel_text: str
    name: str = "世界观"


class RetentionBody(BaseModel):
    hook: str = ""
    conflict: str = ""
    climax: str = ""
    ending: str = ""
    retention_strategy: str = ""


class RetentionPlanBody(BaseModel):
    episodes: list[dict] = []


@router.post("/executive-producer")
def executive_producer(body: ProducerBody):
    try:
        plan = _producer.plan(
            body.novel_text,
            project_id=body.project_id,
            platform=body.platform,
            budget=body.budget,
            target_episodes=body.target_episodes,
            target_duration=body.target_duration,
            season=body.season,
            write_episodes=body.write_episodes,
        )
        return {
            "plan": plan.to_dict(),
            "pipeline_estimate": _producer.plan_pipeline_estimate(plan),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/episode-planner")
def episode_planner(body: PlannerBody):
    try:
        return _planner.plan_project(body.project_id, body.operator)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/episode-planner/single")
def episode_planner_single(body: SinglePlannerBody):
    try:
        return _planner.plan_episode(body.episode_id, novel_segment=body.novel_segment, operator=body.operator)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/world-analyzer")
def world_analyzer(body: WorldBody):
    try:
        return _world.analyze(body.project_id, body.novel_text, body.name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/retention/score")
def retention_score(body: RetentionBody):
    return _retention.score_episode(**body.model_dump())


@router.post("/retention/plan")
def retention_plan(body: RetentionPlanBody):
    return _retention.score_plan(body.episodes)
