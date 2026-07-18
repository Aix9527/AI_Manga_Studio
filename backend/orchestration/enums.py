from enum import Enum


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class JobStatus(_ValueEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StepStatus(_ValueEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"
    CANCELLED = "cancelled"


LEGAL_JOB_TRANSITIONS = {
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


def _normalize_job_status(value: JobStatus | str) -> JobStatus:
    try:
        return JobStatus(value)
    except (TypeError, ValueError):
        raise ValueError(f"unknown job status: {value}") from None


def assert_transition(current: JobStatus | str, target: JobStatus | str) -> None:
    normalized_current = _normalize_job_status(current)
    normalized_target = _normalize_job_status(target)
    if normalized_target not in LEGAL_JOB_TRANSITIONS[normalized_current]:
        raise ValueError(
            f"illegal job transition: {normalized_current} -> {normalized_target}"
        )
