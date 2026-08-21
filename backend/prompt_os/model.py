"""Prompt OS data model (Phase 13.6, GPT spec).

Prompt 操作系统把提示词从"一段文本"升级为可组合、复用、版本化、
自动优化的生产资产：Prompt DNA 知识库 + 八层 ShotDesign + Prompt
Compiler + 十引擎注册表 + Prompt Evolution（人工审批门）。

沿用全局冻结约束：auto_learning=false / auto_apply=false /
auto_budget_change=false；生产资产只允许新增版本，绝不原地修改。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


DNA_KINDS = [
    "character", "camera", "lens", "scene", "weather", "motion",
    "lighting", "composition", "style", "continuity", "negative",
]

SHOTDESIGN_LAYERS = [
    "story", "director_intent", "photography", "composition",
    "action", "camera_movement", "lighting", "style",
]

SHOTDESIGN_STATUSES = ["draft", "approved", "locked"]
ENGINE_STATUSES = ["active", "disabled"]
EVOLUTION_STATUSES = ["tracking", "candidate", "approved", "rejected", "applied"]


# ---------------------------------------------------------------- DNA
@dataclass
class DNAEntry:
    """One Prompt DNA entry inside a DNA library."""

    id: str
    kind: str = "character"          # character|camera|lens|scene|weather|motion|lighting|composition|style|continuity|negative
    name: str = ""
    description: str = ""
    values: dict = field(default_factory=dict)   # kind-specific structure
    tags: list[str] = field(default_factory=list)
    usage_count: int = 0
    success_score: float = 0.0       # 0..1 accumulated prompt score
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DNAEntry":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------- ShotDesign
@dataclass
class ContinuityContract:
    """跨镜连续性约束（GPT 修改建议 1）：跨镜头继承/必须一致的状态。"""

    characters: dict = field(default_factory=dict)   # {character_id: {state, costume, expression, position}}
    props: dict = field(default_factory=dict)        # {prop_id: {state, position}}
    space: dict = field(default_factory=dict)        # {location: {time, weather, layout}}
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ContinuityContract":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ShotDesign:
    """八层电影 Prompt 语言（GPT 修改建议 2：Schema 固化为八层并版本化）。"""

    id: str
    version: str = "v1"
    parent_version: str = ""
    layers: dict = field(default_factory=dict)       # SHOTDESIGN_LAYERS keys
    continuity_contract: ContinuityContract = field(default_factory=ContinuityContract)
    transition_in: str = ""                          # 上一镜衔接（转场）
    transition_out: str = ""                         # 下一镜衔接（转场）
    duration_seconds: float = 5.0
    negative_words: list[str] = field(default_factory=list)
    status: str = "draft"                            # draft | approved | locked
    approved_by: str = ""
    approved_at: str = ""
    notes: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def content_hash(self) -> str:
        import hashlib
        blob = "\n".join(
            [
                self.version,
                self.parent_version,
                repr(self.layers),
                repr(self.continuity_contract.to_dict()),
                self.transition_in,
                self.transition_out,
                ",".join(self.negative_words),
            ]
        )
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["continuity_contract"] = self.continuity_contract.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ShotDesign":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        payload = {k: v for k, v in data.items() if k in known}
        cc = payload.pop("continuity_contract", None)
        design = cls(**payload)
        if isinstance(cc, dict):
            design.continuity_contract = ContinuityContract.from_dict(cc)
        return design


# ---------------------------------------------------------------- Evolution
@dataclass
class PromptMetric:
    """单镜头的平台表现指标（完播率/点赞/评论/收藏）。"""

    id: str
    shot_design_id: str
    project_id: str = ""
    episode_id: str = ""
    completion_rate: float = 0.0
    like_rate: float = 0.0
    comment_rate: float = 0.0
    favorite_rate: float = 0.0
    views: int = 0
    created_at: str = field(default_factory=_now)

    def prompt_score(self, weights: dict | None = None) -> float:
        w = weights or {"completion": 0.5, "like": 0.2, "comment": 0.15, "favorite": 0.15}
        return (
            w["completion"] * self.completion_rate
            + w["like"] * self.like_rate
            + w["comment"] * self.comment_rate
            + w["favorite"] * self.favorite_rate
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PromptMetric":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class EvolutionRecord:
    """一次 Prompt 进化记录：指标聚合 → Score → 候选 → 人工审批。"""

    id: str
    shot_design_id: str
    score: float = 0.0
    samples: int = 0
    status: str = "tracking"         # tracking | candidate | approved | rejected | applied
    suggested_layers: dict = field(default_factory=dict)
    reason: str = ""
    reviewer: str = ""
    decided_at: str = ""
    applied_version: str = ""
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvolutionRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------- Engines
@dataclass
class PromptEngine:
    """Prompt OS 十引擎注册表中的一台引擎。"""

    key: str
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    status: str = "active"           # active | disabled
    version: str = "v1"
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PromptEngine":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})