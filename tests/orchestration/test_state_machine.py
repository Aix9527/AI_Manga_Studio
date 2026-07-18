from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import backend.config as config_module
from backend.config import AppConfig, OrchestrationConfig
from backend.orchestration.enums import (
    LEGAL_JOB_TRANSITIONS,
    JobStatus,
    StepStatus,
    assert_transition,
)
from backend.orchestration.schemas import JobCreate, JobStepView, JobView


EXPECTED_JOB_TRANSITIONS = {
    JobStatus.DRAFT: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.CANCELLED},
    JobStatus.RUNNING: {
        JobStatus.RETRY_WAIT,
        JobStatus.WAITING_REVIEW,
        JobStatus.FAILED,
        JobStatus.PAUSED,
        JobStatus.COMPLETED,
        JobStatus.CANCELLED,
    },
    JobStatus.RETRY_WAIT: {
        JobStatus.QUEUED,
        JobStatus.FAILED,
        JobStatus.PAUSED,
        JobStatus.CANCELLED,
    },
    JobStatus.WAITING_REVIEW: {
        JobStatus.QUEUED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    },
    JobStatus.FAILED: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.PAUSED: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.CANCELLED: set(),
}


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


def _job_step_view(**overrides):
    values = {
        "id": "step-1",
        "stage_key": "storyboard",
        "status": StepStatus.PENDING,
        "attempt": 0,
        "progress": 0.0,
    }
    values.update(overrides)
    return JobStepView(**values)


def _job_view(**overrides):
    now = datetime(2026, 1, 1)
    values = {
        "id": "job-1",
        "project_id": "project-1",
        "status": JobStatus.DRAFT,
        "mode": "automatic",
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return JobView(**values)


def test_failed_job_can_resume_but_completed_job_cannot_run_again():
    assert_transition(JobStatus.FAILED, JobStatus.QUEUED)

    with pytest.raises(ValueError, match="illegal job transition: completed -> queued"):
        assert_transition(JobStatus.COMPLETED, JobStatus.QUEUED)


def test_transition_table_has_one_exact_entry_for_every_job_status():
    assert set(LEGAL_JOB_TRANSITIONS) == set(JobStatus)
    assert LEGAL_JOB_TRANSITIONS == EXPECTED_JOB_TRANSITIONS


@pytest.mark.parametrize(
    ("current", "targets"),
    list(EXPECTED_JOB_TRANSITIONS.items()),
)
def test_every_declared_job_transition_is_accepted(current, targets):
    assert LEGAL_JOB_TRANSITIONS[current] == targets
    for target in targets:
        assert_transition(current, target)


def test_terminal_job_statuses_have_no_outgoing_transitions():
    assert LEGAL_JOB_TRANSITIONS[JobStatus.COMPLETED] == set()
    assert LEGAL_JOB_TRANSITIONS[JobStatus.CANCELLED] == set()


def test_transition_accepts_valid_raw_status_strings():
    assert_transition("failed", "queued")


@pytest.mark.parametrize(
    ("current", "target"),
    [("unknown", "queued"), ("failed", "unknown")],
)
def test_transition_rejects_unknown_statuses_with_value_error(current, target):
    with pytest.raises(ValueError, match="unknown job status: unknown"):
        assert_transition(current, target)


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


@pytest.mark.parametrize(
    "project_id",
    [
        "COM\u00b9",
        "COM\u00b9.txt",
        "COM\u00b2",
        "COM\u00b2.txt",
        "COM\u00b3",
        "COM\u00b3.txt",
        "LPT\u00b9",
        "LPT\u00b9.txt",
        "LPT\u00b2",
        "LPT\u00b2.txt",
        "LPT\u00b3",
        "LPT\u00b3.txt",
    ],
)
def test_job_rejects_windows_superscript_device_names(project_id):
    with pytest.raises(ValidationError) as exc_info:
        _job_create(project_id=project_id)

    assert any(error["loc"] == ("project_id",) for error in exc_info.value.errors())


def test_job_accepts_ordinary_unicode_project_name():
    project_id = "\u6f2b\u753b\u9879\u76ee-\u590f\u65e5"

    assert _job_create(project_id=project_id).project_id == project_id


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


@pytest.mark.parametrize("project_id", ["\tproject", "project\n", "project\x7f"])
def test_job_rejects_control_characters_in_raw_project_id(project_id):
    with pytest.raises(ValidationError) as exc_info:
        _job_create(project_id=project_id)

    assert any(error["loc"] == ("project_id",) for error in exc_info.value.errors())


def test_app_config_has_repository_relative_orchestration_database():
    orchestration = AppConfig().orchestration
    expected = (
        Path(config_module.__file__).resolve().parent.parent
        / "database"
        / "orchestration.db"
    )

    assert Path(orchestration.database_path) == expected
    assert orchestration.worker_poll_seconds == 0.5
    assert orchestration.lease_seconds == 30
    assert orchestration.heartbeat_seconds == 10
    assert orchestration.retry_delays_seconds == [5, 15, 45]
    assert orchestration.max_retries == 3


def test_orchestration_retry_delays_are_isolated_between_instances():
    first = OrchestrationConfig()
    second = OrchestrationConfig()

    first.retry_delays_seconds.append(99)

    assert first.retry_delays_seconds == [5, 15, 45, 99]
    assert second.retry_delays_seconds == [5, 15, 45]


@pytest.mark.parametrize("database_path", ["", "   "])
def test_orchestration_rejects_empty_database_path(database_path):
    with pytest.raises(ValidationError) as exc_info:
        OrchestrationConfig(database_path=database_path)

    assert any(error["loc"] == ("database_path",) for error in exc_info.value.errors())


def test_orchestration_trims_database_path():
    assert OrchestrationConfig(database_path="  database/jobs.db  ").database_path == (
        "database/jobs.db"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("worker_poll_seconds", 0),
        ("worker_poll_seconds", -0.1),
        ("lease_seconds", 0),
        ("lease_seconds", -1),
        ("heartbeat_seconds", 0),
        ("heartbeat_seconds", -1),
        ("max_retries", -1),
    ],
)
def test_orchestration_rejects_unsafe_numeric_values(field, value):
    with pytest.raises(ValidationError) as exc_info:
        OrchestrationConfig(**{field: value})

    assert any(error["loc"] == (field,) for error in exc_info.value.errors())


def test_orchestration_rejects_negative_retry_delay():
    with pytest.raises(ValidationError) as exc_info:
        OrchestrationConfig(retry_delays_seconds=[5, -1])

    assert any(
        error["loc"][:1] == ("retry_delays_seconds",)
        for error in exc_info.value.errors()
    )


def test_orchestration_requires_retry_delays_when_retries_are_enabled():
    with pytest.raises(ValidationError, match="retry delays are required"):
        OrchestrationConfig(max_retries=1, retry_delays_seconds=[])


@pytest.mark.parametrize("heartbeat_seconds", [30, 31])
def test_orchestration_requires_heartbeat_before_lease_expiry(heartbeat_seconds):
    with pytest.raises(
        ValidationError,
        match="heartbeat_seconds must be less than lease_seconds",
    ):
        OrchestrationConfig(lease_seconds=30, heartbeat_seconds=heartbeat_seconds)


def test_orchestration_allows_no_retry_delays_when_retries_are_disabled():
    config = OrchestrationConfig(max_retries=0, retry_delays_seconds=[])

    assert config.retry_delays_seconds == []


def test_job_step_rejects_negative_attempt():
    with pytest.raises(ValidationError) as exc_info:
        _job_step_view(attempt=-1)

    assert any(error["loc"] == ("attempt",) for error in exc_info.value.errors())


@pytest.mark.parametrize("progress", [-0.01, 1.01])
def test_job_step_rejects_progress_outside_zero_to_one(progress):
    with pytest.raises(ValidationError) as exc_info:
        _job_step_view(progress=progress)

    assert any(error["loc"] == ("progress",) for error in exc_info.value.errors())


@pytest.mark.parametrize("progress", [-0.01, 1.01])
def test_job_view_rejects_progress_outside_zero_to_one(progress):
    with pytest.raises(ValidationError) as exc_info:
        _job_view(progress=progress)

    assert any(error["loc"] == ("progress",) for error in exc_info.value.errors())


def test_job_progress_accepts_inclusive_boundaries():
    assert _job_step_view(progress=0).progress == 0
    assert _job_step_view(progress=1).progress == 1
    assert _job_view(progress=0).progress == 0
    assert _job_view(progress=1).progress == 1


def test_job_view_restricts_desired_state_without_changing_annotation():
    assert JobView.model_fields["desired_state"].annotation is str
    with pytest.raises(ValidationError) as exc_info:
        _job_view(desired_state="unknown")

    assert any(error["loc"] == ("desired_state",) for error in exc_info.value.errors())
