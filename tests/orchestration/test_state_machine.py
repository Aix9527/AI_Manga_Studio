from pathlib import Path

import pytest
from pydantic import ValidationError

import backend.config as config_module
from backend.config import AppConfig
from backend.orchestration.enums import JobStatus, assert_transition
from backend.orchestration.schemas import JobCreate


def _job_create(**overrides):
    values = {
        "project_id": "project-1",
        "input_path": "novel.txt",
        "input_type": "novel",
        "shot_duration": 5,
        "width": 1080,
        "height": 1920,
        "idempotency_key": "duration-test",
    }
    values.update(overrides)
    return JobCreate(**values)


def test_failed_job_can_resume_but_completed_job_cannot_run_again():
    assert_transition(JobStatus.FAILED, JobStatus.QUEUED)

    with pytest.raises(ValueError, match="illegal job transition: completed -> queued"):
        assert_transition(JobStatus.COMPLETED, JobStatus.QUEUED)


@pytest.mark.parametrize("duration", [4.99, 15.01])
def test_job_rejects_shot_duration_outside_five_to_fifteen_seconds(duration):
    with pytest.raises(ValidationError) as exc_info:
        _job_create(shot_duration=duration)

    duration_errors = [
        error for error in exc_info.value.errors() if error["loc"] == ("shot_duration",)
    ]
    assert duration_errors
    assert any(
        "greater than or equal to 5" in error["msg"]
        or "less than or equal to 15" in error["msg"]
        for error in duration_errors
    )


@pytest.mark.parametrize(
    "project_id",
    [
        "../escape",
        "folder/name",
        "folder\\name",
        "CON",
        "CON.txt",
        "name.",
        "name. ",
    ],
)
def test_job_rejects_project_names_that_cannot_be_safe_windows_folders(project_id):
    with pytest.raises(ValidationError) as exc_info:
        _job_create(project_id=project_id, idempotency_key="safe-name-test")

    assert any(error["loc"] == ("project_id",) for error in exc_info.value.errors())


@pytest.mark.parametrize("duration", [5, 15])
def test_job_accepts_inclusive_shot_duration_boundaries(duration):
    job = _job_create(shot_duration=duration, width=256, height=8192)

    assert job.shot_duration == duration
    assert (job.width, job.height) == (256, 8192)


@pytest.mark.parametrize(("field", "value"), [("width", 257), ("height", 8191)])
def test_job_rejects_odd_video_dimensions(field, value):
    with pytest.raises(ValidationError, match="video dimensions must be even"):
        _job_create(**{field: value})


def test_job_trims_safe_project_id():
    job = _job_create(project_id="  project-safe  ")

    assert job.project_id == "project-safe"


def test_job_trims_project_id_before_applying_length_limit():
    project_id = "a" * 128

    job = _job_create(project_id=f"  {project_id}  ")

    assert job.project_id == project_id


def test_app_config_has_repository_relative_orchestration_database():
    orchestration = AppConfig().orchestration
    expected = (
        Path(config_module.__file__).resolve().parent.parent
        / "database"
        / "orchestration.db"
    )

    assert Path(orchestration.database_path) == expected
    assert orchestration.lease_seconds > 0
    assert orchestration.heartbeat_interval_seconds > 0
    assert orchestration.retry_backoff_seconds
    assert orchestration.max_retries >= 0
