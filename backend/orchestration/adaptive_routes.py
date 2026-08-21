"""Adaptive Dispatcher API (Phase 12.7-A, GPT approved).

Endpoints:
- POST /api/orchestration/adaptive/dispatch       resolve director for one shot
- GET  /api/orchestration/adaptive/ab            100-shot A/B Before vs After
- GET  /api/orchestration/adaptive/failure        failure chain simulation
- GET  /api/orchestration/adaptive/scope         Sci-Fi vs Historical isolation
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.orchestration.adaptive_dispatcher import AdaptiveDispatcher, DispatchRequest

router = APIRouter(prefix="/api/orchestration/adaptive", tags=["adaptive-dispatcher"])

_dispatch: AdaptiveDispatcher | None = None


def get_dispatcher() -> AdaptiveDispatcher:
    global _dispatch
    if _dispatch is None:
        _dispatch = AdaptiveDispatcher()
    return _dispatch


class DispatchBody(BaseModel):
    project: str = ""
    genre: str = "科幻"
    scene_type: str = "action"
    shot_type: str = "medium"
    style: str = ""
    shot_id: str = ""


@router.post("/dispatch")
def dispatch(body: DispatchBody):
    decision = get_dispatcher().dispatch(DispatchRequest(**body.model_dump()))
    return decision.to_dict()


@router.get("/ab")
def ab(limit: int = 100):
    try:
        return get_dispatcher().ab_validation(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/failure")
def failure(unavailable: str = "llm-gpt", genre: str = "科幻", scene_type: str = "action"):
    return get_dispatcher().failure_test(unavailable=unavailable, genre=genre, scene_type=scene_type)


@router.get("/scope")
def scope():
    return get_dispatcher().scope_isolation_report()
