from __future__ import annotations

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import JobStatus, StepStatus
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate, JobSettings, StageExecutionRequest
from backend.orchestration.service import JobService
from backend.orchestration.worker import SSEBroadcaster


def test_completed_job_rewind_clears_terminal_summary_state(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "reset.db"))
    repo = JobRepository(db)
    service = JobService(
        db,
        repo,
        SSEBroadcaster(),
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
        {"stage_key": "planning", "shot_id": ""},
        {"stage_key": "export", "shot_id": ""},
    ])
    with db.transaction() as conn:
        conn.execute(
            """UPDATE jobs
               SET status=?, progress=1.0, final_video='old-final.mp4',
                   finished_at='2026-09-05T00:00:00Z', message='All stages completed.'
               WHERE id=?""",
            (JobStatus.COMPLETED.value, job_id),
        )
        conn.execute(
            "UPDATE job_steps SET status=?, progress=1.0 WHERE job_id=?",
            (StepStatus.COMPLETED.value, job_id),
        )

    result = service.execute_from_stage(
        job_id,
        StageExecutionRequest(stage_key="planning", mode="continue"),
    )

    assert result.status == JobStatus.QUEUED
    assert result.progress == 0.0
    assert result.final_video == ""
    assert result.finished_at is None
    assert result.message == "Stage execution requested: planning (continue)"
