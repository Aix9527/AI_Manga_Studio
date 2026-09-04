from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import JobStatus
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings
from backend.orchestration.service import JobService
from backend.orchestration.worker import SSEBroadcaster
from backend.routes.jobs import router


def _client(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "routes.db"))
    repo = JobRepository(db)
    broadcaster = SSEBroadcaster()
    service = JobService(
        db,
        repo,
        broadcaster,
        OrchestrationConfig(
            database_path=str(tmp_path / "unused.db"),
            checkpoint_dir=str(tmp_path / "checkpoints"),
            project_root=str(tmp_path / "projects"),
        ),
    )
    job_id = repo.create_job(
        JobCreate(project_id="project-a", input_path="chapter.txt"),
        JobSettings(),
    )
    repo.create_steps(job_id, [
        {"stage_key": "load_input", "shot_id": ""},
        {"stage_key": "planning", "shot_id": ""},
        {"stage_key": "visual_generate", "shot_id": "shot_001"},
        {"stage_key": "video_generate", "shot_id": "shot_001"},
        {"stage_key": "composition_compose", "shot_id": ""},
        {"stage_key": "export", "shot_id": ""},
    ])
    with db.transaction() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (JobStatus.PAUSED.value, job_id))
        conn.execute("UPDATE job_steps SET status='completed' WHERE job_id=?", (job_id,))

    app = FastAPI()
    app.state.job_service = service
    app.state.broadcaster = broadcaster
    app.include_router(router)
    return TestClient(app), db, repo, job_id


def test_resume_from_stage_returns_authoritative_same_job(tmp_path):
    client, db, repo, job_id = _client(tmp_path)

    response = client.post(
        f"/api/jobs/{job_id}/resume-from-stage",
        json={"stage_key": "video_generate", "shot_id": "shot_001", "mode": "continue"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["current_stage"] == "video_generate"
    assert body["current_shot"] == "shot_001"


def test_resume_from_stage_rejects_running_job(tmp_path):
    client, db, repo, job_id = _client(tmp_path)
    with db.transaction() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (JobStatus.RUNNING.value, job_id))

    response = client.post(
        f"/api/jobs/{job_id}/resume-from-stage",
        json={"stage_key": "planning", "mode": "continue"},
    )

    assert response.status_code == 409
    assert "running" in response.json()["detail"]


def test_resume_from_stage_requires_shot_for_shot_scoped_stage(tmp_path):
    client, db, repo, job_id = _client(tmp_path)

    response = client.post(
        f"/api/jobs/{job_id}/resume-from-stage",
        json={"stage_key": "video_generate", "mode": "continue"},
    )

    assert response.status_code == 409
    assert "shot_id" in response.json()["detail"]


def test_resume_from_stage_returns_404_for_unknown_target(tmp_path):
    client, db, repo, job_id = _client(tmp_path)

    response = client.post(
        f"/api/jobs/{job_id}/resume-from-stage",
        json={"stage_key": "unknown_stage", "mode": "continue"},
    )

    assert response.status_code == 404
