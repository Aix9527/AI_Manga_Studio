from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"
    CANCELLED = "cancelled"


class JobCommand(str, Enum):
    CREATE = "create"
    PAUSE = "pause"
    RESUME = "resume"
    RETRY = "retry"
    ROLLBACK = "rollback"
    CANCEL = "cancel"


class ReviewAction(str, Enum):
    APPROVE = "approve"
    EDIT = "edit"
    RETRY = "retry"
    ROLLBACK = "rollback"


JOB_TERMINAL = frozenset({JobStatus.COMPLETED, JobStatus.CANCELLED})
JOB_ACTIVE = frozenset({JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRY_WAIT, JobStatus.WAITING_REVIEW})
STEP_INCOMPLETE = frozenset({StepStatus.PENDING, StepStatus.QUEUED, StepStatus.RUNNING, StepStatus.RETRY_WAIT})

STATUS_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.DRAFT: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.WAITING_REVIEW, JobStatus.FAILED, JobStatus.PAUSED, JobStatus.COMPLETED, JobStatus.CANCELLED},
    JobStatus.WAITING_REVIEW: {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.FAILED, JobStatus.PAUSED, JobStatus.CANCELLED},
    JobStatus.RETRY_WAIT: {JobStatus.QUEUED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.FAILED: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.PAUSED: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.CANCELLED: set(),
}

STEP_TRANSITIONS: dict[StepStatus, set[StepStatus]] = {
    StepStatus.PENDING: {StepStatus.QUEUED, StepStatus.CANCELLED},
    StepStatus.QUEUED: {StepStatus.RUNNING, StepStatus.CANCELLED},
    StepStatus.RUNNING: {StepStatus.QUEUED, StepStatus.WAITING_REVIEW, StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.CANCELLED},
    StepStatus.WAITING_REVIEW: {StepStatus.QUEUED, StepStatus.RUNNING, StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.CANCELLED},
    StepStatus.RETRY_WAIT: {StepStatus.QUEUED, StepStatus.FAILED, StepStatus.CANCELLED},
    StepStatus.FAILED: {StepStatus.QUEUED, StepStatus.CANCELLED},
    StepStatus.COMPLETED: {StepStatus.INVALIDATED},
    StepStatus.INVALIDATED: {StepStatus.PENDING, StepStatus.CANCELLED},
    StepStatus.CANCELLED: set(),
}
