"""AI_Manga_Studio v1.0 Phase 1：Production Director（总导演）+ Planner + Scheduler.

总导演：接收需求 → 规划任务树 → 调度 Agent → 状态推进。
不修改现有 v0.8/v0.9 核心生成链路，仅在上层编排。
"""

from __future__ import annotations

from backend.production_v1.model import (
    ALLOWED_TRANSITIONS,
    ProductionProject,
    ProductionState,
    ProductionStore,
    ProductionTask,
    _new_id,
    _now,
)

# GPT Phase 1 影视流程（S0-S14 简化映射）
WORKFLOW_STAGES = [
    ("init", "项目初始化"),
    ("script_analysis", "剧本解析"),
    ("character_design", "角色设计"),
    ("world_building", "世界观构建"),
    ("storyboard", "分镜规划"),
    ("keyframe_generation", "关键帧生成"),
    ("video_generation", "视频生成"),
    ("quality_check", "视觉质检"),
    ("editing", "剪辑"),
    ("audio", "声音"),
    ("final_export", "发布"),
]

# 每个阶段对应的 Agent 类型（GPT Phase 1/2 岗位）
STAGE_AGENTS: dict[str, str] = {
    "script_analysis": "writer",
    "character_design": "character",
    "world_building": "art",
    "storyboard": "director",
    "keyframe_generation": "camera",
    "video_generation": "motion",
    "quality_check": "critic",
    "editing": "editor",
    "audio": "sound",
    "final_export": "producer",
}


class ProductionPlanner:
    """需求 → 生产计划（任务树 / 镜头数 / 资产需求）。"""

    def __init__(self, duration_seconds: int = 300, shot_seconds: int = 5):
        self.duration_seconds = duration_seconds
        self.shot_seconds = shot_seconds

    def plan(self, project: ProductionProject) -> list[ProductionTask]:
        """把一句需求转换为生产任务树。"""
        shots = max(1, round(self.duration_seconds / self.shot_seconds))
        tasks: list[ProductionTask] = []
        for index, (stage, label) in enumerate(WORKFLOW_STAGES):
            if stage == "init":
                continue
            tasks.append(ProductionTask(
                id=_new_id("task"),
                project_id=project.id,
                episode_id="EP001",
                task_type=stage,
                agent_type=STAGE_AGENTS.get(stage, "producer"),
                status="WAITING",
                priority=5 - index,   # 越早优先级越高
                input_data={"stage": stage, "label": label},
            ))
        return tasks


class ProductionScheduler:
    """任务调度：依赖顺序 + 并行分组（GPT Phase 1）。"""

    # 阶段依赖（后一阶段依赖前一阶段完成）
    ORDER = [t[0] for t in WORKFLOW_STAGES[1:]]

    def schedule(self, tasks: list[ProductionTask]) -> dict:
        """按顺序调度；返回并行组列表。"""
        by_type = {t.task_type: t for t in tasks}
        groups: list[list[ProductionTask]] = []
        for stage in self.ORDER:
            task = by_type.get(stage)
            if task:
                groups.append([task])
        return {"groups": groups, "order": self.ORDER}


class ProductionDirector:
    """总导演：创建项目 → 规划 → 调度 → 状态推进。"""

    def __init__(self, store: ProductionStore | None = None,
                 duration_seconds: int = 300, shot_seconds: int = 5):
        self.store = store or ProductionStore()
        self.planner = ProductionPlanner(duration_seconds, shot_seconds)
        self.scheduler = ProductionScheduler()

    def create_project(self, *, name: str, project_type: str = "episode",
                       duration_seconds: int = 300, style: str = "cinematic",
                       target: str = "短剧") -> dict:
        project = ProductionProject(
            id=_new_id("prod"),
            name=name,
            project_type=project_type,
            duration_seconds=duration_seconds,
            style=style,
            target=target,
        )
        # 规划任务树
        tasks = self.planner.plan(project)
        project.tasks = [t.to_dict() for t in tasks]
        self.store.upsert_project(project)
        return project.to_dict()

    def start(self, project_id: str) -> dict:
        project = ProductionProject.from_dict(self.store.get_project(project_id))
        self._transition(project, ProductionState.SCRIPT_ANALYSIS.value)
        # 第一组任务 RUNNING
        for task in project.tasks:
            if task.get("task_type") == "script_analysis":
                task["status"] = "RUNNING"
        project.progress = 8
        self.store.upsert_project(project)
        return self.status(project_id)

    def advance(self, project_id: str, *, stage: str, result: dict | None = None) -> dict:
        """推进到下一阶段（GPT 状态机合法迁移）。"""
        project = ProductionProject.from_dict(self.store.get_project(project_id))
        current = project.state
        # 完成当前阶段任务
        for task in project.tasks:
            if task.get("task_type") == current:
                task["status"] = "SUCCESS"
                task["output_data"] = result or {}
                task["updated_at"] = _now()
        # 找到下一阶段
        order = [t[0] for t in WORKFLOW_STAGES]
        idx = order.index(current) if current in order else 0
        if idx >= len(order) - 1:
            return self.status(project_id)
        next_state = order[idx + 1]
        if next_state not in ALLOWED_TRANSITIONS.get(current, []):
            raise ValueError(f"illegal transition: {current} -> {next_state}")
        project.state = next_state
        for task in project.tasks:
            if task.get("task_type") == next_state:
                task["status"] = "RUNNING"
        project.progress = min(100, int((idx + 1) / (len(order) - 1) * 100))
        self.store.upsert_project(project)
        return self.status(project_id)

    def _transition(self, project: ProductionProject, to_state: str) -> None:
        if to_state not in ALLOWED_TRANSITIONS.get(project.state, []):
            raise ValueError(f"illegal transition: {project.state} -> {to_state}")
        project.state = to_state
        project.updated_at = _now()

    def status(self, project_id: str) -> dict:
        project = self.store.get_project(project_id)
        completed = sum(1 for t in project["tasks"] if t.get("status") in ("SUCCESS", "APPROVED"))
        failed = sum(1 for t in project["tasks"] if t.get("status") == "FAILED")
        return {
            "id": project["id"],
            "name": project["name"],
            "current": project["state"],
            "progress": project["progress"],
            "completed": completed,
            "failed": failed,
            "tasks": project["tasks"],
        }

    def list_projects(self) -> list[dict]:
        return self.store.all_projects()
