
"""Workflows API routes."""

from fastapi import APIRouter, Request

from backend.app.container import ApplicationContainer

router = APIRouter()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    container: ApplicationContainer = request.app.state.container
    job = await container.workflows._job_repo.get(job_id)
    return {"jobId": job.job_id, "jobType": job.job_type, "status": str(job.status),
            "attemptCount": job.attempt_count, "maxAttempts": job.max_attempts}


@router.get("/jobs/pending")
async def list_pending(request: Request):
    container: ApplicationContainer = request.app.state.container
    jobs = await container.workflows._job_repo.list_pending(10)
    return [{"jobId": j.job_id, "jobType": j.job_type, "status": str(j.status)} for j in jobs]
