"""Adaptive Director Router API (Phase 12.6, GPT approved).

Endpoints:
- GET  /api/director/adaptive/proposal          40 scene suggestions (>=30 gate)
- POST /api/director/adaptive/recommendations/{id}/approve
- POST /api/director/adaptive/recommendations/{id}/reject
- POST /api/director/adaptive/rollback          restore adaptive_router_policy_vN
- GET  /api/director/adaptive/ab-validation     >=100-shot Before vs After A/B

``source`` query param: ``mock`` (deterministic synthetic memory stats) or
``production`` (real Director Memory); arena evidence is the same simulated
dataset, keeping tests network-free and deterministic.
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.director.adaptive_router import (
    ADAPTIVE_VERSIONS_DIR,
    DEFAULT_ADAPTIVE_POLICY_PATH,
    AdaptiveDirectorRouter,
)
from backend.director.memory import DirectorMemory

router = APIRouter(prefix="/api/director/adaptive", tags=["director-adaptive"])

PRODUCTION_MEMORY_ROOT = Path("backend/director/memory/storage")
MOCK_MEMORY_ROOT = Path("storage/director_evolution_mock/memory")

_instances: dict[str, AdaptiveDirectorRouter] = {}
_lock = Lock()


class ActionRequest(BaseModel):
    reason: str = ""


def get_router(source: str = "mock") -> AdaptiveDirectorRouter:
    with _lock:
        if source not in _instances:
            if source == "production":
                memory = DirectorMemory(PRODUCTION_MEMORY_ROOT)
                versions_dir = ADAPTIVE_VERSIONS_DIR
            else:
                memory = DirectorMemory(MOCK_MEMORY_ROOT)
                versions_dir = MOCK_MEMORY_ROOT.parent / "adaptive_versions"
            _instances[source] = AdaptiveDirectorRouter(
                policy_path=DEFAULT_ADAPTIVE_POLICY_PATH,
                versions_dir=versions_dir,
                memory_stats=memory.policy.stats(),
            )
        return _instances[source]


# ------------------------------------------------------------- proposal
@router.get("/proposal")
def proposal(source: str = "mock"):
    router = get_router(source)
    data = router.proposal()
    return {
        "source": source,
        "count": data["count"],
        "cells": data["cells"],
        "scope_isolation": data["scope_isolation"],
        "production_value_weights": data["production_value_weights"],
        "recommendations": data["recommendations"],
    }


# ---------------------------------------------------------- approval
@router.post("/recommendations/{rec_id}/approve")
def approve(rec_id: str, body: Optional[ActionRequest] = None, source: str = "mock"):
    router = get_router(source)
    try:
        return router.approve(rec_id, approved_by="human")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/recommendations/{rec_id}/reject")
def reject(rec_id: str, body: Optional[ActionRequest] = None, source: str = "mock"):
    router = get_router(source)
    try:
        return router.reject(
            rec_id, reason=(body.reason if body else ""), rejected_by="human"
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ------------------------------------------------------------ rollback
@router.post("/rollback")
def rollback(body: Optional[ActionRequest] = None, source: str = "mock"):
    router = get_router(source)
    try:
        return router.rollback(
            reason=(body.reason if body else "human_rollback"), rolled_back_by="human"
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ------------------------------------------------------------- A/B
@router.get("/ab-validation")
def ab_validation(limit: int = 100, source: str = "mock"):
    router = get_router(source)
    try:
        return router.ab_validation(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
