"""Production Digital Twin data model (Phase 14.2, GPT spec).

mode=simulation_and_visibility_only / auto_control=false：
Digital Twin 是 KG + Runtime + Analytics 的实时模拟层，不是新的生产系统，
不自动修改任何生产状态（RiskCandidate 仅建议）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


RISK_TYPES = ["episode", "asset", "budget", "schedule", "quality"]
RISK_SEVERITIES = ["low", "medium", "high"]
RISK_STATUSES = ["proposed", "dismissed"]


@dataclass
class RiskCandidate:
    """风险候选（只建议，不自动干预）。"""

    id: str
    risk_type: str = "schedule"
    target_type: str = "episode"
    target_id: str = ""
    severity: str = "medium"
    evidence: dict = field(default_factory=dict)
    suggestion: str = ""
    status: str = "proposed"
    project_id: str = ""
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RiskCandidate":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})
