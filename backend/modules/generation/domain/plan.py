
"""GenerationPlan aggregate - frozen generation contract."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class PlanStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class ReproducibilityLevel(StrEnum):
    EXACT = "exact"
    BEST_EFFORT = "best_effort"
    SEMANTIC = "semantic"
    NONE = "none"


class SeedStrategy(StrEnum):
    RANDOM = "random"
    FIXED = "fixed"
    DERIVE_FROM_TARGET = "derive_from_target"
    DERIVE_FROM_CHARACTER = "derive_from_character"
    DERIVE_FROM_PLAN = "derive_from_plan"
    INCREMENTAL_VARIATIONS = "incremental_variations"
    LOCKED_SERIES = "locked_series"
    PROVIDER_MANAGED = "provider_managed"


@dataclass(frozen=True, slots=True)
class SeedPlan:
    strategy: str
    base_seed: int | None
    candidate_seeds: tuple[int | None, ...]
    derivation_input_hash: str | None
    provider_managed: bool = False


@dataclass(frozen=True, slots=True)
class ReproducibilityContract:
    level: str
    prompt_hash: str
    target_snapshot_hash: str
    character_snapshot_hashes: tuple[str, ...]
    continuity_hash: str | None
    workflow_hash: str | None
    model_hashes: tuple[str, ...]
    input_asset_hashes: tuple[str, ...]
    seed_plan: SeedPlan
    compiler_version: str
    provider_adapter_version: str | None
    known_limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PromptSource:
    source_id: str
    source_type: str
    source_version: str | None
    priority: int
    scope: str
    mandatory: bool
    overridable: bool
    content: dict[str, Any]
    provenance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PromptConflict:
    conflict_id: str
    conflict_type: str
    key: str
    existing_value: Any
    incoming_value: Any
    existing_source_id: str
    incoming_source_id: str
    resolution: str
    selected_value: Any | None
    requires_user_action: bool = False


@dataclass(frozen=True, slots=True)
class PromptProvenanceEntry:
    output_key: str
    output_value: Any
    source_type: str
    source_id: str
    source_version: str | None
    transformation: str | None = None
    resolution_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReferenceCandidate:
    asset_version_id: str
    reference_type: str
    subject_id: str | None
    quality_status: str
    approval_status: str
    similarity_scope: str
    resolution: tuple[int, int] | None
    content_hash: str
    relevance_score: float
    quality_score: float
    continuity_score: float


@dataclass(frozen=True, slots=True)
class PlanDiff:
    old_plan_id: str
    new_plan_id: str
    prompt_changes: tuple[dict[str, Any], ...]
    character_changes: tuple[dict[str, Any], ...]
    scene_changes: tuple[dict[str, Any], ...]
    reference_changes: tuple[dict[str, Any], ...]
    parameter_changes: tuple[dict[str, Any], ...]
    routing_changes: tuple[dict[str, Any], ...]
    seed_changes: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class PlanApproval:
    plan_id: str
    approved_by: str
    approved_at: datetime
    approval_type: str
    acknowledged_warnings: tuple[str, ...]
    approved_snapshot_hash: str


@dataclass(slots=True)
class GenerationPlan:
    plan_id: str
    request_id: str
    project_id: str
    plan_version: int
    parent_plan_id: str | None
    derivation_type: str | None

    generation_type: str
    target_type: str
    target_id: str

    positive_prompt: str
    negative_prompt: str

    logical_parameters: dict[str, Any]
    provider_overrides: dict[str, Any]

    target_snapshot: dict[str, Any]
    character_snapshots: tuple[dict[str, Any], ...]
    scene_snapshot: dict[str, Any] | None
    continuity_snapshot: dict[str, Any] | None

    reference_assets: tuple[dict[str, Any], ...]
    seed_plan: SeedPlan

    prompt_sources: tuple[dict[str, Any], ...]
    prompt_conflicts: tuple[dict[str, Any], ...]
    prompt_provenance: tuple[dict[str, Any], ...]

    routing_decision: dict[str, Any] | None
    reproducibility: ReproducibilityContract | None

    snapshot_hash: str
    status: str = PlanStatus.DRAFT

    approval: PlanApproval | None = None

    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def approve(self, approved_by: str) -> None:
        if self.status not in (PlanStatus.VALIDATED, PlanStatus.NEEDS_REVIEW, PlanStatus.DRAFT):
            raise ValueError(f"Cannot approve plan in status {self.status}")
        self.status = PlanStatus.APPROVED
        self.approval = PlanApproval(
            plan_id=self.plan_id,
            approved_by=approved_by,
            approved_at=datetime.utcnow(),
            approval_type="manual",
            acknowledged_warnings=(),
            approved_snapshot_hash=self.snapshot_hash,
        )

    def mark_queued(self) -> None:
        if self.status != PlanStatus.APPROVED:
            raise ValueError(f"Cannot queue plan in status {self.status}")
        self.status = PlanStatus.QUEUED

    def mark_running(self) -> None:
        self.status = PlanStatus.RUNNING

    def mark_completed(self) -> None:
        self.status = PlanStatus.COMPLETED

    def mark_failed(self) -> None:
        self.status = PlanStatus.FAILED

    def supersede(self) -> None:
        self.status = PlanStatus.SUPERSEDED
