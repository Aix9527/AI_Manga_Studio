
"""Generation domain aggregates."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class GenerationStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    WAITING_REVIEW = "waiting_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(slots=True)
class GenerationRequest:
    request_id: str
    project_id: str
    shot_id: str
    purpose: str
    status: GenerationStatus = GenerationStatus.PENDING
    compiled_prompt: str = ""
    parameters_json: str = "{}"
    snapshot_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    revision: int = 1


@dataclass(slots=True)
class GenerationPlan:
    plan_id: str
    request_id: str
    provider_id: str
    compiled_prompt: str
    parameters_json: str
    snapshot_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())


@dataclass(slots=True)
class GenerationAttempt:
    attempt_id: str
    plan_id: str
    request_id: str
    attempt_number: int
    provider_id: str
    status: str = "pending"
    remote_task_id: str | None = None
    output_asset_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())


@dataclass(slots=True)
class GenerationCandidate:
    candidate_id: str
    attempt_id: str
    request_id: str
    asset_version_id: str
    is_selected: bool = False
    review_status: str = "pending"
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
