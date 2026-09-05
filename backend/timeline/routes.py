from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from backend.timeline.models import (
    TimelineDraftView,
    TimelineMutationResult,
    TimelineOperationRequest,
    TimelineQcRunView,
    TimelineQcStatusView,
    TimelineRevisionRequest,
    TimelineSnapshotView,
    TimelineSummary,
    WaveformEnvelope,
)
from backend.timeline.qc import TimelineQcNotFound, TimelineQcService
from backend.timeline.waveform import WaveformService
from backend.timeline.service import (
    TimelineNotFound,
    TimelineRevisionConflict,
    TimelineRedoUnavailable,
    TimelineService,
    TimelineValidationError,
)
from backend.timeline.media import TimelineMediaIntegrityError, TimelineMediaNotFound


router = APIRouter(tags=["timeline"])


def _service(request: Request) -> TimelineService:
    return request.app.state.timeline_service


def _qc_service(request: Request) -> TimelineQcService:
    return TimelineQcService(_service(request).repo)


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


@router.post("/api/timelines/{timeline_id}/undo", response_model=TimelineMutationResult)
async def undo_timeline_operation(timeline_id: str, value: TimelineRevisionRequest, request: Request) -> TimelineMutationResult:
    try:
        return _service(request).undo(timeline_id, expected_revision=value.expected_revision)
    except TimelineRevisionConflict as error:
        raise HTTPException(status_code=409, detail={"code": "TIMELINE_REVISION_CONFLICT", "message": str(error)}) from error
    except TimelineNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_NOT_FOUND", "message": str(error)}) from error
    except TimelineValidationError as error:
        raise HTTPException(status_code=422, detail={"code": "TIMELINE_HISTORY_UNAVAILABLE", "message": str(error)}) from error


@router.post("/api/timelines/{timeline_id}/redo", response_model=TimelineMutationResult)
async def redo_timeline_operation(timeline_id: str, value: TimelineRevisionRequest, request: Request) -> TimelineMutationResult:
    try:
        return _service(request).redo(timeline_id, expected_revision=value.expected_revision)
    except TimelineRevisionConflict as error:
        raise HTTPException(status_code=409, detail={"code": "TIMELINE_REVISION_CONFLICT", "message": str(error)}) from error
    except TimelineNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_NOT_FOUND", "message": str(error)}) from error
    except (TimelineRedoUnavailable, TimelineValidationError) as error:
        raise HTTPException(status_code=422, detail={"code": "TIMELINE_HISTORY_UNAVAILABLE", "message": str(error)}) from error


@router.post("/api/timelines/{timeline_id}/snapshots", response_model=TimelineSnapshotView, status_code=201)
async def create_timeline_snapshot(timeline_id: str, request: Request) -> TimelineSnapshotView:
    try:
        return _service(request).create_snapshot(timeline_id)
    except TimelineNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_NOT_FOUND", "message": str(error)}) from error
    except (TimelineValidationError, TimelineMediaNotFound, TimelineMediaIntegrityError, ValueError) as error:
        raise HTTPException(status_code=422, detail={"code": "TIMELINE_SNAPSHOT_INVALID", "message": str(error)}) from error


@router.get("/api/timelines/{timeline_id}/snapshots", response_model=list[TimelineSnapshotView])
async def list_timeline_snapshots(timeline_id: str, request: Request) -> list[TimelineSnapshotView]:
    try:
        return _service(request).list_snapshots(timeline_id)
    except TimelineNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_NOT_FOUND", "message": str(error)}) from error


@router.get("/api/timelines/{timeline_id}/snapshots/{snapshot_id}", response_model=TimelineSnapshotView)
async def get_timeline_snapshot(timeline_id: str, snapshot_id: str, request: Request) -> TimelineSnapshotView:
    try:
        return _service(request).get_snapshot(timeline_id, snapshot_id)
    except TimelineNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_SNAPSHOT_NOT_FOUND", "message": str(error)}) from error


@router.post("/api/timeline-snapshots/{snapshot_id}/qc", response_model=TimelineQcRunView)
async def run_timeline_snapshot_qc(snapshot_id: str, request: Request) -> TimelineQcRunView:
    try:
        return _qc_service(request).run(snapshot_id)
    except TimelineQcNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_SNAPSHOT_NOT_FOUND", "message": str(error)}) from error


@router.get("/api/timeline-snapshots/{snapshot_id}/qc", response_model=TimelineQcStatusView)
async def get_timeline_snapshot_qc(snapshot_id: str, request: Request) -> TimelineQcStatusView:
    try:
        return _qc_service(request).get_status(snapshot_id)
    except TimelineQcNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_SNAPSHOT_NOT_FOUND", "message": str(error)}) from error


@router.get("/api/timelines/{timeline_id}/artifacts/{artifact_id}/waveform", response_model=WaveformEnvelope)
async def get_timeline_artifact_waveform(
    timeline_id: str,
    artifact_id: int,
    request: Request,
    bins: int = 512,
) -> WaveformEnvelope:
    service = _service(request)
    timeline = service.repo.get_timeline(timeline_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_NOT_FOUND", "message": "Timeline not found"})
    waveform = WaveformService(
        service.repo.db,
        projects_root=service.repo.projects_root,
    )
    try:
        return waveform.get_or_build(str(timeline["project_id"]), artifact_id, bins=bins)
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": "TIMELINE_WAVEFORM_FAILED", "message": str(error)}) from error
