"""AI_Manga_Studio v1.0 Phase 1：影视生产状态机 + 任务模型.

不改变 v0.8/v0.9 核心生成链路，在上层增加影视生产调度大脑。
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class ProductionState(str, Enum):
    """影视生产状态机（GPT Phase 1 设计）。"""

    INIT = "init"
    SCRIPT_ANALYSIS = "script_analysis"
    CHARACTER_DESIGN = "character_design"
    WORLD_BUILDING = "world_building"
    STORYBOARD = "storyboard"
    KEYFRAME_GENERATION = "keyframe_generation"
    VIDEO_GENERATION = "video_generation"
    QUALITY_CHECK = "quality_check"
    EDITING = "editing"
    AUDIO = "audio"
    FINAL_EXPORT = "final_export"
    DONE = "done"
    FAILED = "failed"


# 合法迁移表
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    ProductionState.INIT.value: [ProductionState.SCRIPT_ANALYSIS.value, ProductionState.FAILED.value],
    ProductionState.SCRIPT_ANALYSIS.value: [ProductionState.CHARACTER_DESIGN.value, ProductionState.FAILED.value],
    ProductionState.CHARACTER_DESIGN.value: [ProductionState.WORLD_BUILDING.value, ProductionState.SCRIPT_ANALYSIS.value, ProductionState.FAILED.value],
    ProductionState.WORLD_BUILDING.value: [ProductionState.STORYBOARD.value, ProductionState.CHARACTER_DESIGN.value, ProductionState.FAILED.value],
    ProductionState.STORYBOARD.value: [ProductionState.KEYFRAME_GENERATION.value, ProductionState.WORLD_BUILDING.value, ProductionState.FAILED.value],
    ProductionState.KEYFRAME_GENERATION.value: [ProductionState.VIDEO_GENERATION.value, ProductionState.STORYBOARD.value, ProductionState.FAILED.value],
    ProductionState.VIDEO_GENERATION.value: [ProductionState.QUALITY_CHECK.value, ProductionState.STORYBOARD.value, ProductionState.FAILED.value],
    ProductionState.QUALITY_CHECK.value: [ProductionState.EDITING.value, ProductionState.VIDEO_GENERATION.value, ProductionState.FAILED.value],
    ProductionState.EDITING.value: [ProductionState.AUDIO.value, ProductionState.QUALITY_CHECK.value, ProductionState.FAILED.value],
    ProductionState.AUDIO.value: [ProductionState.FINAL_EXPORT.value, ProductionState.EDITING.value, ProductionState.FAILED.value],
    ProductionState.FINAL_EXPORT.value: [ProductionState.DONE.value, ProductionState.AUDIO.value, ProductionState.FAILED.value],
    ProductionState.DONE.value: [],
    ProductionState.FAILED.value: [ProductionState.INIT.value],
}

# GPT Phase 1 任务状态
TASK_STATUSES = ["WAITING", "RUNNING", "SUCCESS", "FAILED", "RETRY", "APPROVED"]


@dataclass
class ProductionProject:
    """影视生产项目。"""

    id: str
    name: str = ""
    project_type: str = "episode"
    duration_seconds: int = 300
    style: str = "cinematic"
    target: str = "短剧"
    state: str = ProductionState.INIT.value
    tasks: list = field(default_factory=list)
    progress: int = 0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProductionProject":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ProductionTask:
    """生产任务（GPT Phase 1 模型）。"""

    id: str
    project_id: str = ""
    episode_id: str = ""
    task_type: str = ""
    agent_type: str = ""
    status: str = "WAITING"
    priority: int = 3
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    retry_count: int = 0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProductionTask":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


class ProductionStore:
    """JSON 持久化（与现有 storage 风格一致）。"""

    def __init__(self, root: str | Path = "storage/production_v1"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._projects: dict[str, dict] = self._load("projects.json")

    def _load(self, name: str) -> dict[str, dict]:
        path = self.root / name
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _save(self, name: str, data: dict[str, dict]) -> None:
        path = self.root / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def upsert_project(self, project: ProductionProject) -> ProductionProject:
        with self._lock:
            self._projects[project.id] = project.to_dict()
            self._save("projects.json", self._projects)
        return project

    def get_project(self, project_id: str) -> dict:
        with self._lock:
            raw = self._projects.get(project_id)
        if not raw:
            raise KeyError(f"project not found: {project_id}")
        return dict(raw)

    def all_projects(self) -> list[dict]:
        with self._lock:
            return [dict(raw) for raw in self._projects.values()]
