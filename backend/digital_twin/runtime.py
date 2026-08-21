"""Runtime Mirror + Timeline + Heatmap (Phase 14.2 A/B/C).

只读读取 Worker/TaskQueue/TeamAssignment/ProductionEvent，输出
Current Production State / Episode 甘特图 / Resource Heatmap。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _load_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


class RuntimeMirror:
    """A. Current Production State（Worker / TaskQueue / Assignment 镜像）。"""

    def __init__(self, root: str | Path = "storage"):
        self.root = Path(root)

    def _tasks(self) -> dict:
        raw = _load_dict(self.root / "tasks" / "tasks.json")
        return raw.get("tasks", raw) if isinstance(raw, dict) else raw

    def _assignments(self) -> dict:
        return _load_dict(self.root / "team" / "assignments.json")

    def current_state(self, project_id: str | None = None) -> dict:
        tasks = self._tasks()
        assignments = self._assignments()
        task_status: dict[str, int] = {}
        workers: dict[str, dict] = {}
        total_gpu_s = 0.0
        for row in tasks.values():
            if project_id and row.get("project_id") != project_id:
                continue
            status = row.get("status", "unknown")
            task_status[status] = task_status.get(status, 0) + 1
            worker_id = row.get("worker_id", "")
            if worker_id:
                w = workers.setdefault(worker_id, {"tasks": 0, "gpu_time_s": 0.0, "active": 0})
                w["tasks"] += 1
                w["gpu_time_s"] += row.get("gpu_time_s", 0) or 0
                if status in ("running", "queued"):
                    w["active"] += 1
            total_gpu_s += row.get("gpu_time_s", 0) or 0

        asg_status: dict[str, int] = {}
        waiting_human = 0
        for row in assignments.values():
            if project_id and row.get("project_id") != project_id:
                continue
            status = row.get("status", "")
            asg_status[status] = asg_status.get(status, 0) + 1
            if status == "escalated":
                waiting_human += 1
        active_tasks = task_status.get("running", 0) + task_status.get("queued", 0)
        idle_workers = max(0, len(workers) - active_tasks) if workers else 0
        return {
            "tasks": task_status,
            "task_total": sum(task_status.values()),
            "active_tasks": active_tasks,
            "workers": {wid: {"tasks": w["tasks"], "active": w["active"], "gpu_time_s": round(w["gpu_time_s"], 2)} for wid, w in workers.items()},
            "worker_count": len(workers),
            "worker_idle_rate": round(idle_workers / len(workers), 3) if workers else 0.0,
            "gpu_time_s_total": round(total_gpu_s, 2),
            "assignments": asg_status,
            "assignment_active": asg_status.get("in_progress", 0) + asg_status.get("assigned", 0),
            "waiting_human": waiting_human,
            "queue_depth": task_status.get("queued", 0),
        }


class TimelineBuilder:
    """B. Episode 甘特图（KG/Team 数据 → 阶段时间线）。"""

    def __init__(self, root: str | Path = "storage"):
        self.root = Path(root)

    def timeline(self, project_id: str | None = None) -> dict:
        assignments = _load_dict(self.root / "team" / "assignments.json")
        episodes: dict[str, dict] = {}
        for row in assignments.values():
            if project_id and row.get("project_id") != project_id:
                continue
            ep = row.get("episode_id", "")
            episode = episodes.setdefault(ep, {
                "episode_id": ep,
                "stages": [],
                "blocked_count": 0,
                "rework_count": 0,
                "waiting_human": 0,
            })
            started = row.get("started_at", "")
            completed = row.get("completed_at", "")
            duration_s = None
            if started and completed:
                try:
                    t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                    duration_s = max(0, int((t1 - t0).total_seconds()))
                except Exception:  # noqa: BLE001
                    duration_s = None
            episode["stages"].append({
                "stage": row.get("stage", ""),
                "role": row.get("role", ""),
                "status": row.get("status", ""),
                "started_at": started,
                "completed_at": completed,
                "duration_s": duration_s,
                "attempt": row.get("attempt", 1),
                "rework_count": row.get("rework_count", 0),
                "blocked_reason": row.get("blocked_reason", ""),
            })
            if row.get("blocked_reason"):
                episode["blocked_count"] += 1
            if row.get("rework_count", 0) > 0:
                episode["rework_count"] += row.get("rework_count", 0)
            if row.get("status") == "escalated":
                episode["waiting_human"] += 1
        for episode in episodes.values():
            episode["stages"].sort(key=lambda s: s["stage"])
        return {
            "episodes": sorted(episodes.values(), key=lambda e: e["episode_id"]),
            "blocked_total": sum(e["blocked_count"] for e in episodes.values()),
            "rework_total": sum(e["rework_count"] for e in episodes.values()),
            "waiting_human_total": sum(e["waiting_human"] for e in episodes.values()),
        }


class HeatmapBuilder:
    """C. Resource Heatmap（GPU / Worker / 生产密度）。"""

    def __init__(self, root: str | Path = "storage"):
        self.root = Path(root)
        self.mirror = RuntimeMirror(root)

    def heatmap(self, project_id: str | None = None) -> dict:
        state = self.mirror.current_state(project_id=project_id)
        assignments = _load_dict(self.root / "team" / "assignments.json")
        episodes: set[str] = set()
        retry_hotspots: dict[str, int] = {}
        stage_density: dict[str, int] = {}
        for row in assignments.values():
            if project_id and row.get("project_id") != project_id:
                continue
            if row.get("status") not in ("done", "cancelled", "failed"):
                episodes.add(row.get("episode_id", ""))
            stage = row.get("stage", "")
            stage_density[stage] = stage_density.get(stage, 0) + 1
            if row.get("rework_count", 0) > 0:
                retry_hotspots[row.get("stage", "")] = retry_hotspots.get(row.get("stage", ""), 0) + 1
            if row.get("attempt", 1) > 1:
                retry_hotspots[row.get("stage", "")] = retry_hotspots.get(row.get("stage", ""), 0) + 1
        gpu_usage = 0.0
        if state["worker_count"] > 0:
            gpu_usage = round(state["active_tasks"] / max(1, state["worker_count"] * 2), 3)  # 简化：每 worker 2 槽
        return {
            "gpu": {
                "usage": min(1.0, gpu_usage),
                "vram_mb": round(state["gpu_time_s_total"] * 0.4, 1),  # 简化估算
                "queue_length": state["queue_depth"],
                "worker_idle_rate": state["worker_idle_rate"],
                "active_tasks": state["active_tasks"],
            },
            "production": {
                "parallel_episodes": len(episodes),
                "assignment_density": state["assignment_active"],
                "stage_density": stage_density,
                "retry_hotspots": dict(sorted(retry_hotspots.items(), key=lambda kv: kv[1], reverse=True)),
            },
        }
