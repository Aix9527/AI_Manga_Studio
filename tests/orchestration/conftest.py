from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate


@pytest.fixture
def job_repo(tmp_path):
    return JobRepository(OrchestrationDatabase(tmp_path / "orchestration.db"))


def create_job(
    repository: JobRepository,
    key: str,
    *,
    mode: str = "automatic",
) -> dict:
    return repository.create_job(
        JobCreate(
            project_id=key,
            input_path=f"{key}.txt",
            input_type="novel",
            mode=mode,
            idempotency_key=f"request-{key}",
        )
    )


def insert_step(
    repository: JobRepository,
    job_id: str,
    *,
    sequence: int = 0,
    status: str = "queued",
    stage_key: str = "input_parse",
    attempt: int = 0,
    finished_at: str | None = None,
) -> str:
    step_id = str(uuid4())
    with repository.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO job_steps(
                id, job_id, sequence, stage_key, shot_id, status,
                attempt, finished_at
            ) VALUES (?, ?, ?, ?, '', ?, ?, ?)
            """,
            (
                step_id,
                job_id,
                sequence,
                stage_key,
                status,
                attempt,
                finished_at,
            ),
        )
    return step_id


def set_job(repository: JobRepository, job_id: str, **values: object) -> None:
    if not values:
        return
    assignments = ", ".join(f"{column}=?" for column in values)
    with repository.database.transaction() as connection:
        connection.execute(
            f"UPDATE jobs SET {assignments} WHERE id=?",
            (*values.values(), job_id),
        )


@pytest.fixture
def queued_job(job_repo):
    job = create_job(job_repo, "queued")
    insert_step(job_repo, job["id"])
    return job


@pytest.fixture
def running_job(job_repo):
    job = create_job(job_repo, "running")
    set_job(
        job_repo,
        job["id"],
        status="running",
        worker_id="dead-worker",
        lease_until="2000-01-01T00:00:00+00:00",
    )
    insert_step(
        job_repo,
        job["id"],
        status="completed",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    insert_step(
        job_repo,
        job["id"],
        sequence=1,
        status="running",
        stage_key="script_plan",
    )
    return job
