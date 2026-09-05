from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from backend.timeline.models import (
    TimelineDraftView,
    TimelineMutationResult,
    TimelineOperationRequest,
    TimelineSummary,
)
from backend.timeline.service import (
    TimelineNotFound,
    TimelineRevisionConflict,
    TimelineService,
    TimelineValidationError,
)


router = APIRouter(tags=["timeline"])


def _service(request: Request) -> TimelineService:
    return request.app.state.timeline_service


@router.get("/api/projects/{project_id}/timeline", response_model=TimelineSummary)
async def get_project_timeline(project_id: str, request: Request) -> TimelineSummary:
    timeline = _service(request).get_project_timeline(project_id)
    if timeline is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "TIMELINE_NOT_FOUND", "message": "Timeline does not exist for project"},
        )
    return timeline


@router.post("/api/projects/{project_id}/timeline/initialize", response_model=TimelineDraftView)
async def initialize_project_timeline(project_id: str, request: Request, response: Response) -> TimelineDraftView:
    draft, created = _service(request).initialize_project(project_id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return draft


@router.get("/api/timelines/{timeline_id}/draft", response_model=TimelineDraftView)
async def get_timeline_draft(timeline_id: str, request: Request) -> TimelineDraftView:
    try:
        return _service(request).get_draft(timeline_id)
    except TimelineNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "TIMELINE_NOT_FOUND", "message": str(error)},
        ) from error


@router.post("/api/timelines/{timeline_id}/operations", response_model=TimelineMutationResult)
async def apply_timeline_operation(
    timeline_id: str,
    value: TimelineOperationRequest,
    request: Request,
) -> TimelineMutationResult:
    try:
        return _service(request).apply_operation(timeline_id, value)
    except TimelineNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "TIMELINE_NOT_FOUND", "message": str(error)},
        ) from error
    except TimelineRevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "TIMELINE_REVISION_CONFLICT", "message": str(error)},
        ) from error
    except TimelineValidationError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "TIMELINE_VALIDATION_FAILED", "message": str(error)},
        ) from error
