"""Multi-Project Production Orchestrator data model (Phase 13.5-A, GPT spec).

Season Manager / Project Resource Planner / GPU Queue Optimizer / Budget
Controller / Parallel Episode Scheduler. All recommendations are human-gated:
no auto budget changes, no auto publishing (GPT risk #2).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


SEASON_STATUSES = ["planning", "production", "paused", "review", "completed"]
RESOURCE_STATUSES = ["draft", "active", "paused", "archived"]
BUDGET_STATUSES = ["ok", "warning", "exceeded"]
PLAN_STATUSES = ["draft", "approved", "dispatched", "rejected"]


@dataclass
class Season:
    id: str
    project_id: str = ""
    season_no: int = 1
    name: str = ""
    target_episodes: int = 0
    status: str = "planning"
    episode_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Season":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ProjectResource:
    id: str
    project_id: str = ""
    season_id: str = ""
    gpu_capacity: int = 1
    gpu_allocated: int = 0
    budget_allocated: float = 0.0
    deadline: str = ""
    priority: int = 3                # 1-5
    status: str = "draft"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectResource":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class BudgetPolicy:
    project_id: str
    monthly_limit: float = 0.0
    episode_limit: float = 0.0
    warning_threshold: float = 0.8
    hard_limit: float = 1.0
    override_requires_approval: bool = True
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BudgetPolicy":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class BudgetEntry:
    id: str
    project_id: str = ""
    amount: float = 0.0
    source: str = "cost_meter"
    note: str = ""
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BudgetEntry":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class EpisodeDependency:
    episode_id: str
    requires: list[str] = field(default_factory=list)
    previous_episode_asset: str = ""
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EpisodeDependency":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class SchedulePlan:
    id: str
    project_id: str = ""
    status: str = "draft"            # draft | approved | dispatched | rejected
    scheduled: list[str] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)
    parallelism: int = 1
    reviewer: str = ""
    created_at: str = field(default_factory=_now)
    decided_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SchedulePlan":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})