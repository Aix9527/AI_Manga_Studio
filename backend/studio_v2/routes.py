"""v1.0 Phase 3-9 聚合 API（/api/v1/*）. """

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.consistency.engine import CinemaJudge, IdentityLock, MotionMemory, RepairEngine, SceneMemory, StyleLock
from backend.studio.factory import ProductionFactory
from backend.evolution.engine import DirectorEvolution, FailurePattern, PromptEvolution
from backend.studio_v2.platform import (
    CreativeBrain, FilmCertifier, IPManager, ProjectManager, RenderScheduler,
    StudioCouncil, TemplateMarket, WorkerRegistry,
)
from backend.studio_v2.shots import list_shots

router = APIRouter(prefix="/api/v1", tags=["v1-phases"])

# ------------------------------------------------------------- Phase 3
_identity = IdentityLock()
_scene = SceneMemory()
_style = StyleLock()
_motion = MotionMemory()
_repair = RepairEngine()
_judge = CinemaJudge()


class IdentityBody(BaseModel):
    character: str
    fixed: dict = {}
    observed: dict = {}
    face_similarity: float = 1.0


@router.get("/shots")
def shots():
    return list_shots()


@router.post("/consistency/identity/register")
def identity_register(body: IdentityBody):
    return _identity.register(character=body.character, fixed=body.fixed)


@router.post("/consistency/identity/check")
def identity_check(body: IdentityBody):
    return _identity.check(character=body.character, observed=body.observed,
                           face_similarity=body.face_similarity)


class RepairBody(BaseModel):
    shot_id: str
    issues: list[str] = []


@router.post("/consistency/repair")
def repair(body: RepairBody):
    return _repair.repair(shot_id=body.shot_id, issues=body.issues)


class ScoreBody(BaseModel):
    visual_quality: float = 0
    character: float = 0
    motion: float = 0
    cinematic_language: float = 0
    emotion: float = 0
    continuity: float = 0


@router.post("/consistency/cinema-score")
def cinema_score(body: ScoreBody):
    return _judge.score(visual_quality=body.visual_quality, character=body.character,
                        motion=body.motion, cinematic_language=body.cinematic_language,
                        emotion=body.emotion, continuity=body.continuity)


# ------------------------------------------------------------- Phase 4
_factory = ProductionFactory()


class SeasonBody(BaseModel):
    title: str
    content: str = ""
    characters: list[str] = []
    locations: list[str] = []
    episodes: int = 12
    shots_per_episode: int = 60


@router.post("/studio/season-plan")
def season_plan(body: SeasonBody):
    return _factory.produce_season_plan(
        title=body.title, content=body.content, characters=body.characters,
        locations=body.locations, episodes=body.episodes,
        shots_per_episode=body.shots_per_episode,
    )


# ------------------------------------------------------------- Phase 5
_evolution = DirectorEvolution()
_prompt_evolve = PromptEvolution()
_failure = FailurePattern()


class LearnBody(BaseModel):
    pattern_type: str
    solution: dict = {}
    score: float = 0
    prompt: str = ""
    improved: str = ""
    failure_type: str = ""
    cause: str = ""
    fix: str = ""


@router.post("/evolution/learn")
def evolution_learn(body: LearnBody):
    result = _evolution.learn(pattern_type=body.pattern_type, solution=body.solution, score=body.score)
    if body.prompt:
        _prompt_evolve.evolve(key=body.pattern_type, prompt=body.prompt,
                              score=body.score, improved=body.improved or body.prompt)
    if body.failure_type:
        _failure.record(failure_type=body.failure_type, cause=body.cause, fix=body.fix)
    return result


@router.get("/evolution/direct/{pattern_type}")
def evolution_direct(pattern_type: str):
    return _evolution.direct(pattern_type)


# ------------------------------------------------------------- Phase 6-9
_project = ProjectManager()
_ip = IPManager()
_template = TemplateMarket()
_council = StudioCouncil()
_brain = CreativeBrain()
_workers = WorkerRegistry()
_scheduler = RenderScheduler()
_certifier = FilmCertifier()


class ProjectBody(BaseModel):
    owner_id: str
    name: str
    project_type: str
    genre: str = ""
    style: str = ""


@router.post("/platform/project")
def platform_project(body: ProjectBody):
    try:
        return _project.create(owner_id=body.owner_id, name=body.name,
                               project_type=body.project_type, genre=body.genre, style=body.style)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class CeoBody(BaseModel):
    trend: str = "玄幻"
    audience: str = "18-35 男性"


@router.post("/company/ceo-decide")
def ceo_decide(body: CeoBody):
    return _council.ceo_decide(market_signals={"trend": body.trend, "audience": body.audience})


@router.get("/company/templates")
def templates(category: str | None = None):
    return _template.list(category)


class WorkerBody(BaseModel):
    worker_id: str
    worker_type: str
    gpu: str
    memory_gb: int
    models: list[str] = []


@router.post("/infra/worker/register")
def worker_register(body: WorkerBody):
    return _workers.register(worker_id=body.worker_id, worker_type=body.worker_type,
                             gpu=body.gpu, memory_gb=body.memory_gb, models=body.models)


@router.get("/infra/workers")
def workers(worker_type: str | None = None, model: str | None = None):
    return {"workers": _workers.find(worker_type=worker_type, model=model)}


class CertifyBody(BaseModel):
    technical: float = 0
    character: float = 0
    motion: float = 0
    cinematic: float = 0
    audience: float = 0


@router.post("/infra/certify")
def certify(body: CertifyBody):
    return _certifier.certify(technical=body.technical, character=body.character,
                              motion=body.motion, cinematic=body.cinematic, audience=body.audience)


class IdeaBody(BaseModel):
    market: list[str] = []


@router.post("/creative/ideas")
def ideas(body: IdeaBody):
    return {"ideas": _brain.generate_ideas(market=body.market or ["玄幻", "复仇", "穿越"])}
