"""Production Readiness Matrix API (Phase 13.4-B, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.production.readiness_matrix import ProductionReadinessMatrix

router = APIRouter(prefix="/api/readiness-matrix", tags=["readiness-matrix"])

_matrix = ProductionReadinessMatrix()


@router.get("/{project_id}")
def check_matrix(project_id: str):
    try:
        return _matrix.check_project(project_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))