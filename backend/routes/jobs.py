from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.orchestration.schemas import (
    JobCreate,
    JobDetail,
    JobListResponse,
    RetryRequest,
    ReviewRequest,
    JobCommandRequest,
    StageExecutionRequest,
    RollbackPreview,
)
from backend.orchestration.repository import ReviewJobNotFound, ReviewTransitionConflict
from backend.orchestration.service import (
    JobService,
    StageExecutionConflict,
    StageExecutionTargetNotFound,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def get_service(request: Request) -> JobService:
    svc = request.app.state.job_service
    if svc is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return svc


@router.post("", response_model=JobDetail, status_code=201)
async def create_job(data: JobCreate, request: Request) -> JobDetail:
    result = get_service(request).create(data)
    return result


@router.get("", response_model=JobListResponse)
async def list_jobs(
    request: Request,
    project_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> JobListResponse:
    return get_service(request).list_jobs(project_id=project_id, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, request: Request) -> JobDetail:
    detail = get_service(request).get_job(job_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return detail


@router.post("/{job_id}/pause", response_model=JobDetail)
async def pause_job(job_id: str, request: Request) -> JobDetail:
    return get_service(request).pause(job_id)


@router.post("/{job_id}/resume", response_model=JobDetail)
async def resume_job(job_id: str, request: Request) -> JobDetail:
    return get_service(request).resume(job_id)


@router.post("/{job_id}/retry", response_model=JobDetail)
async def retry_job(job_id: str, body: RetryRequest, request: Request) -> JobDetail:
    return get_service(request).retry(job_id, step_id=body.step_id)


@router.post("/{job_id}/resume-from-stage", response_model=JobDetail)
async def resume_from_stage(
    job_id: str,
    body: StageExecutionRequest,
    request: Request,
) -> JobDetail:
    try:
        return get_service(request).execute_from_stage(job_id, body)
    except StageExecutionTargetNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StageExecutionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{job_id}/cancel", response_model=JobDetail)
async def cancel_job(job_id: str, request: Request) -> JobDetail:
    return get_service(request).cancel(job_id)


@router.post("/{job_id}/review", response_model=JobDetail)
async def review_job(job_id: str, body: ReviewRequest, request: Request) -> JobDetail:
    try:
        return get_service(request).review(
            job_id,
            action=body.action,
            comment=body.comment,
            patch=body.patch,
        )
    except ReviewJobNotFound as error:
        raise HTTPException(status_code=404, detail="任务不存在") from error
    except ReviewTransitionConflict as error:
        raise HTTPException(status_code=409, detail="任务当前不处于待审核状态") from error


@router.get("/{job_id}/rollback-preview", response_model=RollbackPreview)
async def rollback_preview(job_id: str, request: Request, step_id: str = Query(...)) -> RollbackPreview:
    return get_service(request).rollback_preview(job_id, step_id)


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    service = get_service(request)
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    broadcaster = request.app.state.broadcaster

    async def event_generator():
        import queue
        q = broadcaster.subscribe(job_id)
        try:
            initial = {
                "event": "initial",
                "data": json.dumps({
                    "job_id": job_id,
                    "status": job.status,
                    "progress": job.progress,
                    "current_stage": job.current_stage,
                }),
            }
            yield f"event: {initial['event']}\ndata: {initial['data']}\n\n"

            while True:
                try:
                    payload = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: q.get(timeout=30)
                    )
                    parsed = json.loads(payload)
                    yield f"event: {parsed['event']}\ndata: {json.dumps(parsed['data'])}\n\n"
                except queue.Empty:
                    yield "event: heartbeat\ndata: {}\n\n"

                updated = service.get_job(job_id)
                if updated and updated.status in ("completed", "failed", "cancelled"):
                    yield f"event: terminal\ndata: {json.dumps({'status': updated.status})}\n\n"
                    break
        finally:
            broadcaster.unsubscribe(job_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )