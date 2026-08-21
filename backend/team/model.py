"""Team Collaboration data model (Phase 13.5-C, GPT spec).

9 角色制作团队 + TeamAssignment 状态机（含 blocked / failed / escalated /
rework）+ ReviewRecord + 定向返工路由 + append-only TeamAudit。

治理约束（GPT 批复）：human_approval=true / rollback=true / audit=true /
auto_learning=false / auto_apply=false / auto_deploy=false /
auto_budget_change=false；复用 TaskQueue/Worker/LeaseLock/CostMeter，
新建队列 0。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- roles
ROLES = [
    "Producer", "Planner", "Writer", "Director", "Editor", "Sound",
    "Production", "Reviewer", "Analyst",
]

ROLE_RESPONSIBILITIES = {
    "Producer": "资源、预算、进度和关键审批",
    "Planner": "集规划、留存结构和依赖拆解",
    "Writer": "剧本、对白和旁白",
    "Director": "分镜、镜头语言和导演指令",
    "Editor": "时间线、节奏、转场和成片结构",
    "Sound": "配音、环境声、音乐、混音和同步",
    "Production": "TaskQueue、Worker、生成与资源执行",
    "Reviewer": "Critic、Quality、Identity和规则评审",
    "Analyst": "Production Intelligence与候选建议",
}

# 前端泳道：策划｜编剧｜分镜｜资产｜生成｜质检｜剪辑｜声音｜成片
STAGES = [
    "planning", "script", "storyboard", "assets", "generation",
    "qc", "editing", "sound", "final",
]

STAGE_LABELS = {
    "planning": "策划", "script": "编剧", "storyboard": "分镜", "assets": "资产",
    "generation": "生成", "qc": "质检", "editing": "剪辑", "sound": "声音",
    "final": "成片",
}

# 阶段 → Review Owner（角色评审）
STAGE_REVIEW_OWNER = {
    "planning": "Producer",
    "script": "Planner",
    "storyboard": "Director",
    "assets": "Director",
    "generation": "Reviewer",
    "qc": "Reviewer",
    "editing": "Editor",
    "sound": "Sound",
    "final": "Producer",
}

ASSIGNEE_TYPES = ["agent", "human", "service"]

# ---------------------------------------------------------------- status
STATUSES = [
    "planned", "assigned", "in_progress", "review", "approved", "done",
    "rework", "blocked", "failed", "escalated", "cancelled",
]

# GPT 批准的主要迁移表（禁止 planned→done / in_progress→approved / rework→done）
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "planned": ["assigned", "cancelled"],
    "assigned": ["in_progress", "blocked", "cancelled"],
    "in_progress": ["review", "failed", "blocked"],
    "review": ["approved", "rework", "escalated"],
    "rework": ["assigned", "escalated"],
    "approved": ["done"],
    "blocked": ["assigned", "cancelled"],
    "escalated": ["assigned", "failed"],
}

FORBIDDEN_TRANSITIONS = [
    ("planned", "done"),
    ("in_progress", "approved"),
    ("rework", "done"),
]

REVIEW_VERDICTS = ["approve", "reject", "request_changes", "escalate"]

# ---------------------------------------------------------------- rework
REWORK_ROUTING = {
    "character_identity": "asset_or_generation",
    "prompt_adherence": "prompt",
    "motion": "director_or_generation",
    "lighting": "prompt_or_generation",
    "continuity": "storyboard_or_director",
    "audio_sync": "sound_or_editor",
    "pacing": "editor",
    "budget": "producer",
}

# 问题分类 → 目标 stage
REWORK_TARGET_STAGE: dict[str, str] = {
    "character_identity": "generation",
    "prompt_adherence": "planning",
    "motion": "storyboard",
    "lighting": "generation",
    "continuity": "storyboard",
    "audio_sync": "sound",
    "pacing": "editing",
    "budget": "planning",
}

# 问题分类 → 目标角色
REWORK_TARGET_ROLE: dict[str, str] = {
    "character_identity": "Production",
    "prompt_adherence": "Writer",
    "motion": "Director",
    "lighting": "Production",
    "continuity": "Director",
    "audio_sync": "Sound",
    "pacing": "Editor",
    "budget": "Producer",
}

REWORK_POLICY = {
    "default_max_attempts": 2,
    "generation_max_attempts": 3,
    "prompt_revision_max_attempts": 2,
    "qc_failure_escalation": True,
}

# ---------------------------------------------------------------- models
@dataclass
class Team:
    """制作团队（单项目，v0.1 scope）。"""

    id: str
    project_id: str = ""
    season_id: str = ""
    name: str = ""
    members: list = field(default_factory=list)
    role_bindings: dict = field(default_factory=dict)
    status: str = "active"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Team":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class TeamAssignment:
    """单个协作任务（状态机 planned→…→done）。"""

    id: str
    project_id: str = ""
    season_id: str = ""
    episode_id: str = ""
    stage: str = "planning"
    role: str = "Producer"
    assignee_type: str = "agent"      # agent | human | service
    assignee_id: str = ""
    status: str = "planned"
    input_artifacts: list = field(default_factory=list)
    output_artifacts: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    task_id: str = ""
    checkpoint_id: str = ""
    attempt: int = 1
    max_attempts: int = 2
    rework_count: int = 0
    blocked_reason: str = ""
    deadline: str = ""
    created_at: str = field(default_factory=_now)
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TeamAssignment":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ReviewRecord:
    """评审记录（Automated Gate + Role Review 结果）。"""

    id: str
    assignment_id: str = ""
    reviewer_role: str = "Reviewer"
    reviewer_id: str = ""
    verdict: str = "approve"          # approve | reject | request_changes | escalate
    rule_results: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    comments: str = ""
    next_stage: str = ""
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class TeamAudit:
    """append-only 审计记录（禁止覆盖/删除）。"""

    id: str
    project_id: str = ""
    episode_id: str = ""
    assignment_id: str = ""
    event: str = ""
    actor: str = ""
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    reason: str = ""
    evidence: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TeamAudit":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})
