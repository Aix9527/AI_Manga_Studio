"""Multi-Project Orchestrator stores (Phase 13.5-A) — JSON persistence."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from backend.multi_project.models import (
    BudgetEntry,
    BudgetPolicy,
    EpisodeDependency,
    ProjectResource,
    SchedulePlan,
    Season,
)

_ROOT = "storage/multi_project"


class _JsonStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def get(self, key: str) -> dict | None:
        with self._lock:
            raw = self._data.get(key)
        return dict(raw) if raw else None

    def all(self) -> list[dict]:
        with self._lock:
            return [dict(raw) for raw in self._data.values()]

    def put(self, key: str, value: dict) -> dict:
        with self._lock:
            self._data[key] = value
            self._save()
        return value


class MultiProjectStore:
    def __init__(self, root: str | Path = _ROOT):
        root = Path(root)
        self.seasons = _JsonStore(root / "seasons.json")
        self.resources = _JsonStore(root / "resources.json")
        self.budget_policies = _JsonStore(root / "budget_policies.json")
        self.budget_ledger = _JsonStore(root / "budget_ledger.json")
        self.dependencies = _JsonStore(root / "dependencies.json")
        self.plans = _JsonStore(root / "plans.json")
        self.audit = _JsonStore(root / "audit.json")

    # ------------------------------------------------------------- seasons
    def put_season(self, season: Season) -> Season:
        self.seasons.put(season.id, season.to_dict())
        return season

    def get_season(self, season_id: str) -> Season | None:
        raw = self.seasons.get(season_id)
        return Season.from_dict(raw) if raw else None

    def list_seasons(self, project_id: str | None = None) -> list[Season]:
        rows = [Season.from_dict(r) for r in self.seasons.all()]
        if project_id:
            rows = [r for r in rows if r.project_id == project_id]
        return sorted(rows, key=lambda r: r.season_no)

    # ------------------------------------------------------------- resources
    def put_resource(self, resource: ProjectResource) -> ProjectResource:
        self.resources.put(resource.id, resource.to_dict())
        return resource

    def get_resource(self, resource_id: str) -> ProjectResource | None:
        raw = self.resources.get(resource_id)
        return ProjectResource.from_dict(raw) if raw else None

    def list_resources(self, project_id: str | None = None) -> list[ProjectResource]:
        rows = [ProjectResource.from_dict(r) for r in self.resources.all()]
        if project_id:
            rows = [r for r in rows if r.project_id == project_id]
        return rows

    # ------------------------------------------------------------- budget
    def put_policy(self, policy: BudgetPolicy) -> BudgetPolicy:
        self.budget_policies.put(policy.project_id, policy.to_dict())
        return policy

    def get_policy(self, project_id: str) -> BudgetPolicy | None:
        raw = self.budget_policies.get(project_id)
        return BudgetPolicy.from_dict(raw) if raw else None

    def put_entry(self, entry: BudgetEntry) -> BudgetEntry:
        self.budget_ledger.put(entry.id, entry.to_dict())
        return entry

    def list_entries(self, project_id: str | None = None) -> list[BudgetEntry]:
        rows = [BudgetEntry.from_dict(r) for r in self.budget_ledger.all()]
        if project_id:
            rows = [r for r in rows if r.project_id == project_id]
        return sorted(rows, key=lambda r: r.created_at)

    # ------------------------------------------------------------- scheduler
    def put_dependency(self, dep: EpisodeDependency) -> EpisodeDependency:
        self.dependencies.put(dep.episode_id, dep.to_dict())
        return dep

    def get_dependency(self, episode_id: str) -> EpisodeDependency | None:
        raw = self.dependencies.get(episode_id)
        return EpisodeDependency.from_dict(raw) if raw else None

    def put_plan(self, plan: SchedulePlan) -> SchedulePlan:
        self.plans.put(plan.id, plan.to_dict())
        return plan

    def get_plan(self, plan_id: str) -> SchedulePlan | None:
        raw = self.plans.get(plan_id)
        return SchedulePlan.from_dict(raw) if raw else None

    def list_plans(self, project_id: str | None = None) -> list[SchedulePlan]:
        rows = [SchedulePlan.from_dict(r) for r in self.plans.all()]
        if project_id:
            rows = [r for r in rows if r.project_id == project_id]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    # ------------------------------------------------------------- audit
    def audit_entry(self, action: str, target: str, detail: str = "", actor: str = "system") -> dict:
        row = {"action": action, "target": target, "detail": detail, "actor": actor, "at": _now()}
        key = f"{row['at']}-{len(row['detail'])}-{hash(detail) % 10000}"
        self.audit.put(key, row)
        return row

    def list_audit(self, limit: int = 100) -> list[dict]:
        rows = list(self.audit.all())
        rows.sort(key=lambda r: r.get("at", ""), reverse=True)
        return rows[:limit]


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")