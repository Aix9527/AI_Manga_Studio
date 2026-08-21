"""Production OS API（v1.0 Phase 1）. """

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.production_v1.director import ProductionDirector
from backend.production_v1.sse import broadcast_status, sse

router = APIRouter(prefix="/api/production", tags=["production-v1"])

_director = ProductionDirector()


def _http(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=422, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


class CreateBody(BaseModel):
    name: str
    project_type: str = "episode"
    duration_seconds: int = 300
    style: str = "cinematic"
    target: str = "短剧"


class AdvanceBody(BaseModel):
    stage: str = ""
    result: dict = {}


@router.post("/create")
async def create_project(body: CreateBody):
    try:
        result = _director.create_project(
            name=body.name, project_type=body.project_type,
            duration_seconds=body.duration_seconds, style=body.style, target=body.target,
        )
        await broadcast_status(result["id"], result)
        return result
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/start/{project_id}")
async def start(project_id: str):
    try:
        result = _director.start(project_id)
        await broadcast_status(project_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.post("/advance/{project_id}")
async def advance(project_id: str, body: AdvanceBody):
    try:
        result = _director.advance(project_id, stage=body.stage, result=body.result)
        await broadcast_status(project_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/status/{project_id}")
def status(project_id: str):
    try:
        return _director.status(project_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc)


@router.get("/events")
async def events():
    return StreamingResponse(sse.subscribe(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/projects")
def list_projects():
    return {"projects": _director.list_projects()}
