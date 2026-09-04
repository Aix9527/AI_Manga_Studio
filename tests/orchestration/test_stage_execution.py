from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.enums import JobStatus, StepStatus
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import (
    JobCreate,
    JobSettings,
    StageExecutionRequest,
)
from backend.orchestration.service import JobService
from backend.orchestration.worker import SSEBroadcaster


STAGES = [
    {"stage_key": "load_input", "shot_id": ""},
    {"stage_key": "planning", "shot_id": ""},
    {"stage_key": "character_design", "shot_id": ""},
    {"stage_key": "visual_generate", "shot_id": "shot_001"},
    {"stage_key": "hd_redraw", "shot_id": "shot_001"},
    {"stage_key": "video_generate", "shot_id": "shot_001"},
    {"stage_key": "visual_generate", "shot_id": "shot_002"},
    {"stage_key": "hd_redraw", "shot_id": "shot_002"},
    {"stage_key": "video_generate", "shot_id": "shot_002"},
    {"stage_key": "audio_tts", "shot_id": ""},
    {"stage_key": "audio_sfx", "shot_id": ""},
    {"stage_key": "composition_compose", "shot_id": ""},
    {"stage_key": "export", "shot_id": ""},
]


def _system(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "stage-execution.db"))
    repo = JobRepository(db)
    broadcaster = SSEBroadcaster()
    config = OrchestrationConfig(
        database_path=str(tmp_path / "unused.db"),
        checkpoint_dir=str(tmp_path / "checkpoints"),
        project_root=str(tmp_path / "projects"),
    )
    service = JobService(db, repo, broadcaster, config)
    job_id = repo.create_job(
        JobCreate(project_id="project-a", input_path="chapter.txt"),
        JobSettings(),
    )
    repo.create_steps(job_id, STAGES)
    return db, repo, service, job_id


def _force_job_status(db: OrchestrationDatabase, job_id: str, status: JobStatus) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status.value, job_id))


def _complete_all_steps(db: OrchestrationDatabase, job_id: str) -> None:
    with db.transaction() as conn:
        conn.execute(
            "UPDATE job_steps SET status=? WHERE job_id=?",
            (StepStatus.COMPLETED.value, job_id),
        )


def _steps(repo: JobRepository, job_id: str):
    return {(row["stage_key"], row["shot_id"]): row for row in repo.get_job_steps(job_id)}


def test_stage_execution_request_accepts_only_formal_modes():
    request = StageExecutionRequest(
        stage_key="video_generate",
        shot_id="shot_001",
        mode="continue",
    )
    assert request.mode == "continue"

    with pytest.raises(ValidationError):
        StageExecutionRequest(stage_key="video_generate", shot_id="shot_001", mode="fake")


def test_shot_scoped_stage_requires_shot_id(tmp_path):
    db, repo, service, job_id = _system(tmp_path)
    _force_job_status(db, job_id, JobStatus.PAUSED)

    with pytest.raises(ValueError, match="shot_id"):
        service.execute_from_stage(
            job_id,
            StageExecutionRequest(stage_key="video_generate", mode="continue"),
        )


def test_waiting_review_fails_closed_without_step_mutation(tmp_path):
    db, repo, service, job_id = _system(tmp_path)
    _complete_all_steps(db, job_id)
    _force_job_status(db, job_id, JobStatus.WAITING_REVIEW)
    before = [(row["id"], row["status"]) for row in repo.get_job_steps(job_id)]

    with pytest.raises(ValueError, match="waiting_review"):
        service.execute_from_stage(
            job_id,
            StageExecutionRequest(stage_key="planning", mode="continue"),
        )

    after = [(row["id"], row["status"]) for row in repo.get_job_steps(job_id)]
    assert after == before


def test_continue_from_one_shot_reopens_only_its_visual_path_and_global_outputs(tmp_path):
    db, repo, service, job_id = _system(tmp_path)
    _complete_all_steps(db, job_id)
    _force_job_status(db, job_id, JobStatus.PAUSED)

    result = service.execute_from_stage(
        job_id,
        StageExecutionRequest(
            stage_key="visual_generate",
            shot_id="shot_001",
            mode="continue",
        ),
    )

    current = _steps(repo, job_id)
    assert result.id == job_id
    assert result.status == JobStatus.QUEUED
    assert current[("visual_generate", "shot_001")]["status"] == StepStatus.QUEUED
    assert current[("hd_redraw", "shot_001")]["status"] == StepStatus.PENDING
    assert current[("video_generate", "shot_001")]["status"] == StepStatus.PENDING
    assert current[("visual_generate", "shot_002")]["status"] == StepStatus.COMPLETED
    assert current[("hd_redraw", "shot_002")]["status"] == StepStatus.COMPLETED
    assert current[("video_generate", "shot_002")]["status"] == StepStatus.COMPLETED
    assert current[("audio_tts", "")]["status"] == StepStatus.PENDING
    assert current[("audio_sfx", "")]["status"] == StepStatus.PENDING
    assert current[("composition_compose", "")]["status"] == StepStatus.PENDING
    assert current[("export", "")]["status"] == StepStatus.PENDING


def test_rerun_node_leaves_downstream_dependencies_invalidated(tmp_path):
    db, repo, service, job_id = _system(tmp_path)
    _complete_all_steps(db, job_id)
    _force_job_status(db, job_id, JobStatus.PAUSED)

    result = service.execute_from_stage(
        job_id,
        StageExecutionRequest(
            stage_key="video_generate",
            shot_id="shot_001",
            mode="rerun_node",
        ),
    )

    current = _steps(repo, job_id)
    assert result.status == JobStatus.QUEUED
    assert current[("video_generate", "shot_001")]["status"] == StepStatus.QUEUED
    assert current[("video_generate", "shot_002")]["status"] == StepStatus.COMPLETED
    assert current[("audio_tts", "")]["status"] == StepStatus.INVALIDATED
    assert current[("audio_sfx", "")]["status"] == StepStatus.INVALIDATED
    assert current[("composition_compose", "")]["status"] == StepStatus.INVALIDATED
    assert current[("export", "")]["status"] == StepStatus.INVALIDATED


def test_planning_continue_reopens_every_later_stage(tmp_path):
    db, repo, service, job_id = _system(tmp_path)
    _complete_all_steps(db, job_id)
    _force_job_status(db, job_id, JobStatus.FAILED)

    service.execute_from_stage(
        job_id,
        StageExecutionRequest(stage_key="planning", mode="continue"),
    )

    rows = repo.get_job_steps(job_id)
    planning_index = next(i for i, row in enumerate(rows) if row["stage_key"] == "planning")
    assert rows[planning_index]["status"] == StepStatus.QUEUED
    assert all(row["status"] == StepStatus.PENDING for row in rows[planning_index + 1 :])


def test_running_and_queued_jobs_fail_closed(tmp_path):
    for status in (JobStatus.RUNNING, JobStatus.QUEUED):
        db, repo, service, job_id = _system(tmp_path / status.value)
        _force_job_status(db, job_id, status)
        with pytest.raises(ValueError, match=status.value):
            service.execute_from_stage(
                job_id,
                StageExecutionRequest(stage_key="planning", mode="continue"),
            )
