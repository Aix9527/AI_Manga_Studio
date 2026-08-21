"""Multi-Project Production Orchestrator services (Phase 13.5-A, GPT spec).

All GPU/budget/schedule outputs are RECOMMENDATIONS with human approval
gates — no auto budget changes, no auto publishing, no second task queue
(GPT risk #1/#2). TaskQueue / ChainRuntime / Worker / LeaseLock / CostMeter
are reused, never rebuilt.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.multi_project.models import (
    BudgetEntry,
    BudgetPolicy,
    EpisodeDependency,
    ProjectResource,
    SchedulePlan,
    SEASON_STATUSES,
    Season,
)
from backend.multi_project.store import MultiProjectStore
from backend.orchestration.task_queue import TaskQueue
from backend.production.readiness_matrix import ProductionReadinessMatrix
from backend.video.cost_meter import CostMeter


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class SeasonManager:
    """Season lifecycle: planning → production → paused → review → completed."""

    def __init__(self, store: MultiProjectStore):
        self.store = store

    def create_season(self, project_id: str, season_no: int = 1, name: str = "", target_episodes: int = 0) -> Season:
        season = Season(
            id=_new_id("SN"), project_id=project_id, season_no=season_no,
            name=name or f"第{season_no}季", target_episodes=target_episodes,
        )
        self.store.put_season(season)
        self.store.audit_entry("season.create", season.id, f"project={project_id} season_no={season_no}")
        return season

    def list(self, project_id: str | None = None) -> list[Season]:
        return self.store.list_seasons(project_id)

    def get(self, season_id: str) -> Season:
        season = self.store.get_season(season_id)
        if not season:
            raise KeyError(f"season not found: {season_id}")
        return season

    def attach_episode(self, season_id: str, episode_id: str) -> Season:
        season = self.get(season_id)
        if episode_id not in season.episode_ids:
            season.episode_ids.append(episode_id)
            season.updated_at = _now()
            self.store.put_season(season)
            self.store.audit_entry("season.attach_episode", season_id, f"episode={episode_id}")
        return season

    def set_status(self, season_id: str, status: str) -> Season:
        if status not in SEASON_STATUSES:
            raise ValueError(f"invalid season status: {status} (allowed: {SEASON_STATUSES})")
        season = self.get(season_id)
        season.status = status
        season.updated_at = _now()
        self.store.put_season(season)
        self.store.audit_entry("season.status", season_id, status)
        return season

    def stats(self, project_id: str | None = None) -> dict:
        seasons = self.list(project_id)
        return {
            "seasons": len(seasons),
            "episodes_attached": sum(len(s.episode_ids) for s in seasons),
            "by_status": {s: sum(1 for x in seasons if x.status == s) for s in SEASON_STATUSES},
        }


class ProjectResourcePlanner:
    """Project/season GPU + budget resource planning with audit."""

    def __init__(self, store: MultiProjectStore):
        self.store = store

    def plan(
        self,
        project_id: str,
        season_id: str = "",
        gpu_capacity: int = 1,
        budget_allocated: float = 0.0,
        deadline: str = "",
        priority: int = 3,
    ) -> ProjectResource:
        if priority not in range(1, 6):
            raise ValueError("priority must be 1-5")
        resource = ProjectResource(
            id=_new_id("RS"), project_id=project_id, season_id=season_id,
            gpu_capacity=gpu_capacity, budget_allocated=budget_allocated,
            deadline=deadline, priority=priority,
        )
        self.store.put_resource(resource)
        self.store.audit_entry("resource.plan", resource.id, f"project={project_id} gpu={gpu_capacity} budget={budget_allocated}")
        return resource

    def list(self, project_id: str | None = None) -> list[ProjectResource]:
        return self.store.list_resources(project_id)

    def update(self, resource_id: str, **fields) -> ProjectResource:
        resource = self.store.get_resource(resource_id)
        if not resource:
            raise KeyError(f"resource not found: {resource_id}")
        for key, value in fields.items():
            if value is not None and hasattr(resource, key):
                setattr(resource, key, value)
        resource.updated_at = _now()
        self.store.put_resource(resource)
        self.store.audit_entry("resource.update", resource_id, str(fields))
        return resource

    def stats(self) -> dict:
        rows = self.list()
        return {
            "projects": len({r.project_id for r in rows}),
            "resources": len(rows),
            "gpu_capacity": sum(r.gpu_capacity for r in rows),
            "gpu_allocated": sum(r.gpu_allocated for r in rows),
            "budget_allocated": round(sum(r.budget_allocated for r in rows), 2),
        }


class GPUQueueOptimizer:
    """Recommend-only GPU queue ranking over the existing TaskQueue.

    schedule_score = priority_weight + deadline_weight + gpu_fit_score
    + retry_penalty. Never mutates the queue directly (GPT risk #2).
    """

    def __init__(self, store: MultiProjectStore, task_queue: TaskQueue | None = None):
        self.store = store
        self.task_queue = task_queue or TaskQueue()

    def recommend(self, limit: int = 10, gpu_capacity: int = 1) -> dict:
        tasks = self.task_queue.list(status="queued")
        scored = [self._score(task) for task in tasks]
        scored.sort(key=lambda row: row["score"], reverse=True)
        ranked = scored[:limit]
        return {
            "queued": len(tasks),
            "recommended": ranked,
            "gpu_capacity": gpu_capacity,
            "note": "推荐仅参考；调度需人工审批后执行",
        }

    def _score(self, task: Any) -> dict:
        priority = int(getattr(task, "priority", 0) or 0)
        deadline = self._deadline_factor(task)
        gpu_fit = self._gpu_fit_score(task)
        retry_penalty = int(getattr(task, "attempts", 0) or 0) * -0.2
        score = round(priority * 2.0 + deadline + gpu_fit + retry_penalty, 3)
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "project_id": task.project_id,
            "priority": priority,
            "deadline_factor": deadline,
            "gpu_fit_score": gpu_fit,
            "retry_penalty": retry_penalty,
            "score": score,
        }

    @staticmethod
    def _deadline_factor(task: Any) -> float:
        raw = getattr(task, "payload", {}) or {}
        deadline = raw.get("deadline", "")
        if not deadline:
            return 0.0
        try:
            target = datetime.fromisoformat(deadline)
            days = (target - datetime.now()).total_seconds() / 86400.0
            if days < 0:
                return 3.0
            if days < 1:
                return 2.0
            if days < 3:
                return 1.0
        except (ValueError, TypeError):
            pass
        return 0.0

    @staticmethod
    def _gpu_fit_score(task: Any) -> float:
        payload = getattr(task, "payload", {}) or {}
        vram = float(payload.get("vram_peak_gb", 0.0) or 0.0)
        if vram <= 0:
            return 0.5
        if vram <= 12:
            return 1.0
        if vram <= 24:
            return 0.7
        return 0.3


class BudgetController:
    """Budget policy + ledger + CostMeter integration. Over-budget → WARNING
    with producer approval gate (never auto-stop / auto-change budget)."""

    def __init__(self, store: MultiProjectStore, cost_meter: CostMeter | None = None):
        self.store = store
        self.cost_meter = cost_meter or CostMeter()

    def set_policy(
        self,
        project_id: str,
        monthly_limit: float,
        episode_limit: float = 0.0,
        warning_threshold: float = 0.8,
        hard_limit: float = 1.0,
        override_requires_approval: bool = True,
    ) -> BudgetPolicy:
        policy = BudgetPolicy(
            project_id=project_id, monthly_limit=monthly_limit,
            episode_limit=episode_limit, warning_threshold=warning_threshold,
            hard_limit=hard_limit, override_requires_approval=override_requires_approval,
        )
        self.store.put_policy(policy)
        self.store.audit_entry("budget.set_policy", project_id, f"monthly={monthly_limit}")
        return policy

    def get_policy(self, project_id: str) -> BudgetPolicy:
        policy = self.store.get_policy(project_id)
        if not policy:
            raise KeyError(f"budget policy not found: {project_id}")
        return policy

    def record_cost(self, project_id: str, amount: float, source: str = "cost_meter", note: str = "") -> dict:
        entry = BudgetEntry(
            id=_new_id("BD"), project_id=project_id, amount=amount,
            source=source, note=note,
        )
        self.store.put_entry(entry)
        self.store.audit_entry("budget.cost", project_id, f"amount={amount}")
        return self.summary(project_id)

    def summary(self, project_id: str) -> dict:
        policy = self.store.get_policy(project_id)
        entries = self.store.list_entries(project_id)
        spent = round(sum(e.amount for e in entries), 4)
        status = "ok"
        ratio = 0.0
        if policy and policy.monthly_limit > 0:
            ratio = round(spent / policy.monthly_limit, 4)
            if ratio >= policy.hard_limit:
                status = "exceeded"
            elif ratio >= policy.warning_threshold:
                status = "warning"
        cost_summary = self.cost_meter.summary()
        return {
            "project_id": project_id,
            "spent": spent,
            "monthly_limit": policy.monthly_limit if policy else 0.0,
            "ratio": ratio,
            "status": status,
            "entries": len(entries),
            "cost_meter_shots": cost_summary["shots"],
            "cost_meter_gpu_time_s": cost_summary["total_gpu_time_s"],
        }

    def authorize(self, project_id: str, amount: float) -> dict:
        summary = self.summary(project_id)
        if summary["status"] == "exceeded":
            return {
                "allowed": False, "status": "exceeded",
                "requires_approval": True,
                "reason": "预算已超硬上限，需 Producer 审批覆盖",
            }
        if summary["status"] == "warning" and summary["monthly_limit"] > 0:
            return {
                "allowed": True, "status": "warning",
                "requires_approval": summary["ratio"] + (amount / summary["monthly_limit"]) >= summary["hard_limit"],
                "reason": "接近预算上限",
            }
        return {"allowed": True, "status": "ok", "requires_approval": False, "reason": ""}

    def approve_override(self, project_id: str, reviewer: str) -> dict:
        policy = self.get_policy(project_id)
        if not policy.override_requires_approval:
            raise ValueError("policy does not require override approval")
        self.store.audit_entry("budget.override_approved", project_id, f"reviewer={reviewer}")
        return {"project_id": project_id, "approved": True, "reviewer": reviewer, "at": _now()}


class ParallelEpisodeScheduler:
    """Dependency-aware parallel episode planning (recommend + human gate).

    Checks Asset Ready → Prompt Ready → Resource Ready → Production Ready
    by reusing the 13.4 Production Readiness Matrix (GPT spec).
    """

    def __init__(
        self,
        store: MultiProjectStore,
        readiness_matrix: ProductionReadinessMatrix | None = None,
        seasons: SeasonManager | None = None,
        resources: ProjectResourcePlanner | None = None,
        task_queue: TaskQueue | None = None,
    ):
        self.store = store
        self.readiness = readiness_matrix or ProductionReadinessMatrix()
        self.seasons = seasons or SeasonManager(store)
        self.resources = resources or ProjectResourcePlanner(store)
        self.task_queue = task_queue or TaskQueue()

    def register_dependency(self, episode_id: str, requires: list[str], previous_episode_asset: str = "") -> dict:
        dep = EpisodeDependency(
            episode_id=episode_id, requires=requires or [],
            previous_episode_asset=previous_episode_asset,
        )
        self.store.put_dependency(dep)
        return dep.to_dict()

    def build_plan(self, project_id: str, max_parallel: int = 2) -> dict:
        matrix = self.readiness.check_project(project_id)
        resource = self.resources.list(project_id)
        gpu_capacity = resource[0].gpu_capacity if resource else 1
        scheduled: list[str] = []
        blocked: list[dict] = []
        episode_ids = [
            eid
            for season in self.seasons.list(project_id)
            for eid in season.episode_ids
        ]
        previous_done = True
        for episode_id in episode_ids:
            reasons: list[str] = []
            if matrix["status"] != "READY":
                reasons.append("production_not_ready")
            dep = self.store.get_dependency(episode_id)
            if dep:
                for required in dep.requires:
                    if required not in (scheduled + episode_ids):
                        reasons.append(f"missing_dependency:{required}")
            if not previous_done:
                reasons.append("previous_episode_asset_pending")
            if len(scheduled) >= max_parallel:
                reasons.append("parallel_limit")
            if reasons:
                blocked.append({"episode_id": episode_id, "reasons": reasons})
                previous_done = False
            else:
                scheduled.append(episode_id)
                previous_done = True
        plan = SchedulePlan(
            id=_new_id("PL"), project_id=project_id, scheduled=scheduled,
            blocked=blocked, parallelism=min(max_parallel, gpu_capacity),
        )
        self.store.put_plan(plan)
        return plan.to_dict()

    def approve_plan(self, plan_id: str, reviewer: str) -> dict:
        plan = self.store.get_plan(plan_id)
        if not plan:
            raise KeyError(f"plan not found: {plan_id}")
        if plan.status not in ("draft", "rejected"):
            raise ValueError(f"plan already {plan.status}")
        plan.status = "approved"
        plan.reviewer = reviewer
        plan.decided_at = _now()
        self.store.put_plan(plan)
        self.store.audit_entry("schedule.approve", plan_id, f"reviewer={reviewer}")
        return plan.to_dict()

    def dispatch_plan(self, plan_id: str, task_queue: TaskQueue | None = None) -> dict:
        plan = self.store.get_plan(plan_id)
        if not plan:
            raise KeyError(f"plan not found: {plan_id}")
        if plan.status != "approved":
            raise ValueError(f"only approved plans can dispatch (status={plan.status})")
        queue = task_queue or self.task_queue or TaskQueue()
        dispatched: list[str] = []
        for episode_id in plan.scheduled:
            task = queue.enqueue(
                "video_chain", {"episode_id": episode_id, "project_id": plan.project_id},
                project_id=plan.project_id, priority=3,
            )
            dispatched.append(task.task_id)
        plan.status = "dispatched"
        plan.decided_at = _now()
        self.store.put_plan(plan)
        self.store.audit_entry("schedule.dispatch", plan_id, f"tasks={len(dispatched)}")
        return {"plan_id": plan_id, "dispatched": dispatched, "status": plan.status}

    def list_plans(self, project_id: str | None = None) -> list[dict]:
        return [p.to_dict() for p in self.store.list_plans(project_id)]


class MultiProjectOrchestrator:
    """Facade bundling all 13.5-A managers."""

    def __init__(
        self,
        root: str | Path = "storage/multi_project",
        *,
        task_queue: TaskQueue | None = None,
        cost_meter: CostMeter | None = None,
        readiness_matrix: ProductionReadinessMatrix | None = None,
    ):
        self.store = MultiProjectStore(root)
        self.seasons = SeasonManager(self.store)
        self.resources = ProjectResourcePlanner(self.store)
        self.gpu_queue = GPUQueueOptimizer(self.store, task_queue)
        self.budget = BudgetController(self.store, cost_meter)
        self.task_queue = task_queue or TaskQueue()
        self.scheduler = ParallelEpisodeScheduler(
            self.store, readiness_matrix=readiness_matrix,
            seasons=self.seasons, resources=self.resources,
            task_queue=self.task_queue,
        )

    def audit(self, limit: int = 100) -> list[dict]:
        return self.store.list_audit(limit)