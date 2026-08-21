"""Production Pilot API (Phase 15.1)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.production_pilot.feedback_stats import ProductionFeedbackCollector
from backend.production_pilot.pilot import PilotRunner
from backend.production_pilot.snapshot import get_snapshot

router = APIRouter(prefix="/api/production-pilot", tags=["production-pilot"])

_runner = PilotRunner()
_feedback = ProductionFeedbackCollector()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


class RunBody(BaseModel):
    limit: int | None = None
    actor: str = ""
    reason: str = ""


@router.get("/plan")
def plan():
    return _runner.plan()


@router.post("/init")
def init():
    try:
        return _runner.init()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/run")
def run(body: RunBody):
    try:
        return _runner.run_episodes(limit=body.limit)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/seed-events")
def seed_events(body: RunBody):
    try:
        return _runner.seed_events(limit=body.limit)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/feedback")
def feedback():
    return _feedback.report()


@router.post("/feedback/apply-shot-dna")
def apply_shot_dna():
    return _feedback.apply_shot_dna_stats()


@router.get("/report")
def report():
    return _runner.report()

@router.get("/snapshot")
def snapshot():
    """统一口径实时快照（GPT v7.7）：所有报告/文档从同一快照生成。"""
    try:
        return get_snapshot()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)
@router.get("/phase-e")
def phase_e():
    """Phase 15.2-E：导演/Prompt/ShotDNA 三维分析 + DT 校准（auto_apply=false）。"""
    try:
        from backend.production_pilot.phase_e import get_phase_e
        return get_phase_e()
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)