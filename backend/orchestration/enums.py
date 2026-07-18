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


def assert_transition(current: JobStatus, target: JobStatus) -> None:
    if target not in LEGAL_JOB_TRANSITIONS[current]:
        raise ValueError(f"illegal job transition: {current} -> {target}")
