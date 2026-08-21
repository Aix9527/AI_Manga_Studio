"""Digital Twin API (Phase 14.2, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.digital_twin.service import DigitalTwinService

router = APIRouter(prefix="/api/digital-twin", tags=["digital-twin"])

_service = DigitalTwinService()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


class PredictBody(BaseModel):
    project_id: str = ""
    actor: str = ""
    reason: str = ""


class DismissBody(BaseModel):
    actor: str = ""
    reason: str = ""


class SimulateBody(BaseModel):
    scenarios: list[str] = []


@router.get("/overview")
def overview():
    return _service.overview()


@router.get("/state")
def state(project_id: str | None = None):
    return _service.current_state(project_id=project_id)


@router.get("/timeline")
def timeline(project_id: str | None = None):
    return _service.timeline(project_id=project_id)


@router.get("/heatmap")
def heatmap(project_id: str | None = None):
    return _service.heatmap(project_id=project_id)


@router.get("/calibration")
def calibration():
    return _service.calibration()


@router.get("/calibration/state")
def calibration_state():
    return _service.calibration_state()


@router.get("/scenarios")
def scenarios():
    return _service.scenarios()


@router.post("/simulate")
def simulate(body: SimulateBody):
    return _service.simulate(scenario_keys=body.scenarios or None)


@router.post("/predict")
def predict(body: PredictBody):
    try:
        return _service.predict(project_id=body.project_id or None)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/risk-candidates")
def risk_candidates(status: str | None = None):
    return _service.risk_candidates(status=status)


@router.post("/risk-candidates/{candidate_id}/dismiss")
def dismiss(candidate_id: str, body: DismissBody):
    try:
        return _service.dismiss_risk(candidate_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)
