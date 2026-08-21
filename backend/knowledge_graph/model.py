"""Production Knowledge Graph data model (GPT Priority 2).

统一已有数据：Episode / Character / World / Prompt / Shot DNA /
Director Decision / Artifact / Review / Feedback / Production Event /
Team Assignment，建立节点-边图谱，用于跨项目分析、检索与智能推荐。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


NODE_TYPES = [
    "project", "season", "episode", "character", "world", "scene",
    "prompt_version", "shot_dna", "shot", "shot_design", "artifact",
    "review", "feedback", "production_event", "assignment", "candidate",
]

EDGE_TYPES = [
    "BELONGS_TO", "HAS_PHASE", "DEPENDS_ON", "PRODUCED", "REVIEWED_BY",
    "USES", "FEEDBACK_ON", "EVENT_FOR", "SIMILAR_TO", "RELATES_TO",
]


@dataclass
class GraphNode:
    """知识图谱节点。"""

    id: str
    type: str = "episode"
    label: str = ""
    properties: dict = field(default_factory=dict)
    project_id: str = ""
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GraphNode":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class GraphEdge:
    """知识图谱边（source → target）。"""

    id: str
    source: str = ""
    target: str = ""
    type: str = "RELATES_TO"
    properties: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GraphEdge":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})
