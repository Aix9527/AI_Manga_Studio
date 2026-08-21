"""Command Center API (Phase 14.3, GPT spec)."""

from __future__ import annotations

from fastapi import APIRouter

from backend.command_center.service import CommandCenterService

router = APIRouter(prefix="/api/command-center", tags=["command-center"])

_service = CommandCenterService()


@router.get("/overview")
def overview(project_id: str | None = None):
    return _service.overview(project_id=project_id)
