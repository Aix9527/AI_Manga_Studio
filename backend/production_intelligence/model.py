"""Production Intelligence data model (Phase 13.5-B, GPT spec).

B1 EventWarehouse 事实表 + Episode/Shot Metric；B4 Analytics Candidate
沿用人工审批门（auto_learning=false / auto_apply=false），分析与决策
严格分离：Analytics 只产生证据与候选，不直接修改任何生产资产。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


EVENT_TYPES = [
    "generation_start", "generation_end", "qc_failed", "revision_created",
    "approval_passed", "cost_recorded",
]

CANDIDATE_STATUSES = ["proposed", "approved", "rejected", "applied"]
TARGET_TYPES = ["episode", "shot", "director", "prompt_version", "resource"]


@dataclass
class ProductionEvent:
    """Append-only 生产事实事件。"""

    id: str
    event_type: str = "generation_start"   # EVENT_TYPES
    project_id: str = ""
    episode_id: str = ""
    shot_id: str = ""
    actor: str = "pipeline"
    audit_id: str = ""
    payload: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProductionEvent":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ShotMetric:
    """单镜头生产指标（B1 聚合层）。"""

    id: str
    shot_id: str = ""
    episode_id: str = ""
    project_id: str = ""
    director: str = ""
    prompt_version: str = ""
    shot_dna_id: str = ""
    identity_score: float = 0.0
    vision_score: float = 0.0
    motion_score: float = 0.0
    quality: float = 0.0
    revision_count: int = 0
    generation_attempts: int = 0
    cost: float = 0.0
    success: bool = True
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ShotMetric":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class EpisodeMetric:
    """单集生产指标（B1 聚合层）。"""

    id: str
    episode_id: str = ""
    project_id: str = ""
    retention: float = 0.0
    hook_score: float = 0.0
    cliffhanger: float = 0.0
    director_mix: str = ""
    prompt_version: str = ""
    avg_qc: float = 0.0
    failure_rate: float = 0.0
    cost_planned: float = 0.0
    cost_actual: float = 0.0
    lead_time_s: float = 0.0
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EpisodeMetric":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class AnalyticsCandidate:
    """分析结论 → 人工审批候选（B4）。Analytics 不是决策者。"""

    id: str
    target_type: str = "episode"       # TARGET_TYPES
    target_id: str = ""
    project_id: str = ""
    suggested_changes: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    reason: str = ""
    status: str = "proposed"           # proposed | approved | rejected | applied
    reviewer: str = ""
    created_at: str = field(default_factory=_now)
    decided_at: str = ""
    applied_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsCandidate":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})