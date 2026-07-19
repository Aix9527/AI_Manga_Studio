from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate
from backend.orchestration.service import JobService
from backend.routes.jobs import router


@pytest.fixture
def api_database_path(tmp_path):
    return tmp_path / "api.db"


@pytest.fixture
def app_factory(api_database_path):
    def factory(runner=None, *, raise_server_exceptions=True):
        app = FastAPI()
        repository = JobRepository(OrchestrationDatabase(api_database_path))
        app.state.job_service = JobService(
            repository,
            runner or SimpleNamespace(cancel=lambda _job_id: True),
        )
        app.state.sse_poll_seconds = .001
        app.include_router(router)
        return TestClient(
            app, raise_server_exceptions=raise_server_exceptions
        )

    return factory


@pytest.fixture
def client(app_factory):
    return app_factory()


@pytest.fixture
def valid_job_payload():
    return {
        "project_id": "测试项目",
        "input_path": "input/story.txt",
        "input_type": "novel",
        "mode": "automatic",
        "shot_duration": 5,
        "width": 1080,
        "height": 1920,
        "fps": 24,
        "options": {"language": "zh-CN"},
        "idempotency_key": "browser-request-0001",
    }


def insert_step(
    repository,
    job_id,
    sequence=0,
    status="queued",
    *,
    stage_key=None,
    shot_id="",
    attempt=0,
    progress=0,
    input_hash="",
    error_code="",
    error_message="",
    started_at=None,
    finished_at=None,
):
    step_id = str(uuid4())
    with repository.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO job_steps(
                id, job_id, sequence, stage_key, shot_id, status, progress,
                attempt, input_hash, error_code, error_message,
                started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step_id,
                job_id,
                sequence,
                stage_key or f"stage-{sequence}",
                shot_id,
                status,
                progress,
                attempt,
                input_hash,
                error_code,
                error_message,
                started_at,
                finished_at,
            ),
        )
    return step_id


def insert_artifact(repository, job_id, step_id, *, active=1):
    artifact_id = str(uuid4())
    with repository.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO artifacts(
                id, job_id, step_id, kind, path, sha256, size,
                metadata_json, validated_at, active
            ) VALUES (?, ?, ?, 'image', ?, 'abc', 3, '{}', ?, ?)
            """,
            (
                artifact_id,
                job_id,
                step_id,
                f"output/{artifact_id}.png",
                "2026-07-19T00:00:00+00:00",
                active,
            ),
        )
    return artifact_id


def create_job(repository, key, *, mode="automatic"):
    return repository.create_job(
        JobCreate(
            project_id=key,
            input_path=f"{key}.txt",
            input_type="novel",
            mode=mode,
            idempotency_key=f"request-{key}",
        )
    )


def set_job(repository, job_id, **values):
    assignments = ", ".join(f"{key}=?" for key in values)
    with repository.database.transaction() as connection:
        connection.execute(
            f"UPDATE jobs SET {assignments} WHERE id=?",
            (*values.values(), job_id),
        )


def events(repository, job_id):
    return [row["event_type"] for row in repository.list_events(job_id)]
