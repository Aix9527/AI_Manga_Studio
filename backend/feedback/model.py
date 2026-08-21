"""Asset Feedback Loop data model (Phase 13.4-C, GPT spec).

Feedback events are append-only records from Vision Critic / Identity Gate /
Production QC. Candidates are human-reviewed update proposals; only approved
candidates may apply, and they always produce a NEW version of the target
asset (never an in-place mutation of a locked production asset).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


TARGET_TYPES = ["character", "world", "shot_dna", "prompt_template"]
EVENT_KINDS = ["critic", "identity_gate", "qc"]
CANDIDATE_STATUSES = ["proposed", "approved", "rejected", "applied"]


@dataclass
class FeedbackEvent:
    """One append-only feedback record."""

    id: str
    kind: str = "critic"            # critic | identity_gate | qc
    source: str = ""                # e.g. vision_critic, identity_gate, qc_pipeline
    target_type: str = ""           # character | world | shot_dna | prompt_template
    target_id: str = ""
    project_id: str = ""
    severity: str = "medium"        # low | medium | high
    issues: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FeedbackEvent":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class AssetCandidate:
    """Human-reviewed update proposal for an industrial asset."""

    id: str
    target_type: str = ""
    target_id: str = ""
    project_id: str = ""
    suggested_changes: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    reason: str = ""
    status: str = "proposed"        # proposed | approved | rejected | applied
    reviewer: str = ""
    created_at: str = field(default_factory=_now)
    decided_at: str = ""
    applied_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AssetCandidate":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})