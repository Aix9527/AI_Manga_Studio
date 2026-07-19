from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.orchestration.repository import JobConflictError, JobNotFoundError
from backend.orchestration.schemas import (
    JobAction,
    JobCreate,
    ReviewAction,
    RollbackAction,
)


router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


def _service(request: Request):
    return request.app.state.job_service


def _command(operation):
    try:
        return operation()
    except JobNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except JobConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("")
def create_job(command: JobCreate, request: Request):
    return _service(request).create(command)


@router.get("/current")
def current_job(request: Request):
    return _service(request).current()


@router.get("")
def list_jobs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return {"items": _service(request).list(limit, offset)}


@router.get("/{job_id}")
def get_job(job_id: str, request: Request):
    job = _service(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/{job_id}/pause")
def pause_job(job_id: str, request: Request):
    return _command(lambda: _service(request).pause(job_id))


@router.post("/{job_id}/resume")
def resume_job(job_id: str, request: Request):
    return _command(lambda: _service(request).resume(job_id))


@router.post("/{job_id}/retry")
def retry_job(job_id: str, action: JobAction, request: Request):
    return _command(lambda: _service(request).retry(job_id, action.step_id))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    return _command(lambda: _service(request).cancel(job_id))


@router.get("/{job_id}/rollback-preview")
def rollback_preview(job_id: str, step_id: str, request: Request):
    return _command(
        lambda: _service(request).rollback_preview(job_id, step_id)
    )


@router.post("/{job_id}/rollback")
def rollback_job(job_id: str, action: RollbackAction, request: Request):
    return _command(
        lambda: _service(request).rollback(
            job_id, action.step_id, action.confirm_invalidated_step_ids
        )
    )


@router.post("/{job_id}/steps/{step_id}/review")
def review_step(
    job_id: str,
    step_id: str,
    action: ReviewAction,
    request: Request,
):
    return _command(
        lambda: _service(request).review(
            job_id, step_id, action.action, action.comment, action.patch
        )
    )


async def event_stream(
    job_service,
    job_id: str,
    is_disconnected: Callable[[], Awaitable[bool]],
    last_event_id: str = "",
    poll_seconds: float = 1.0,
) -> AsyncIterator[str]:
    previous_id = last_event_id
    while not await is_disconnected():
        job = job_service.get(job_id)
        if job is None:
            yield "event: gone\ndata: {}\n\n"
            return
        payload = json.dumps(
            job,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        snapshot_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if snapshot_id != previous_id:
            previous_id = snapshot_id
            yield f"id: {snapshot_id}\nevent: job\ndata: {payload}\n\n"
        else:
            yield ": keepalive\n\n"
        await asyncio.sleep(poll_seconds)


@router.get("/{job_id}/events")
async def stream_events(
    job_id: str,
    request: Request,
    last_event_id: str = Header(default="", alias="Last-Event-ID"),
):
    poll_seconds = getattr(request.app.state, "sse_poll_seconds", 1.0)
    return StreamingResponse(
        event_stream(
            _service(request),
            job_id,
            request.is_disconnected,
            last_event_id=last_event_id,
            poll_seconds=poll_seconds,
        ),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
