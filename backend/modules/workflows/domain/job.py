
"""Workflow job domain model."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Job:
    job_id: str
    job_type: str
    status: JobStatus
    payload: dict[str, Any]
    priority: int = 0
    attempt_count: int = 0
    max_attempts: int = 3
    leased_by: str | None = None
    lease_expires_at: datetime | None = None
    result_json: str = "{}"
    error_json: str = "{}"
    idempotency_key: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    completed_at: datetime | None = None
    revision: int = 1


@dataclass(slots=True)
class LeaseRecord:
    lease_id: str
    job_id: str
    worker_id: str
    lease_duration_seconds: int = 30
    acquired_at: datetime = field(default_factory=lambda: datetime.utcnow())
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow())
    released_at: datetime | None = None
    status: str = "active"
