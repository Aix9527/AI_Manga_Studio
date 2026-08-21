"""Queue Simulation (Phase 14.2 D, GPT spec).

模拟场景（≥3）：20 集并行 / GPU -50% / Wan 速度 -30% / 返工率 +10%，
输出预计完成时间、成本预测、瓶颈位置。确定性模型，仅模拟不改生产。
"""

from __future__ import annotations

from pathlib import Path

from backend.digital_twin.runtime import RuntimeMirror

SCENARIOS = {
    "baseline": {"label": "基线（当前负载）", "load_factor": 1.0, "capacity_factor": 1.0, "speed_factor": 1.0, "rework_factor": 1.0},
    "20_episodes": {"label": "同时生产 20 集", "load_factor": 20.0, "capacity_factor": 1.0, "speed_factor": 1.0, "rework_factor": 1.0},
    "gpu_minus_50": {"label": "GPU 减少 50%", "load_factor": 1.0, "capacity_factor": 0.5, "speed_factor": 1.0, "rework_factor": 1.0},
    "speed_down_30": {"label": "Wan 生成速度下降 30%", "load_factor": 1.0, "capacity_factor": 1.0, "speed_factor": 1.4286, "rework_factor": 1.0},
    "rework_up_10": {"label": "返工率提高 10%", "load_factor": 1.0, "capacity_factor": 1.0, "speed_factor": 1.0, "rework_factor": 1.1},
}

COST_PER_GPU_HOUR = 2.0  # 假设成本参数（仅模拟）


class QueueSimulator:
    def __init__(self, root: str | Path = "storage"):
        self.root = Path(root)
        self.mirror = RuntimeMirror(root)

    def _baseline_metrics(self) -> dict:
        state = self.mirror.current_state()
        total = state["task_total"] or 1
        active = max(1, state["active_tasks"])
        workers = max(1, state["worker_count"])
        # 单任务平均耗时估算：以 GPU 时间 + 固定耗时兜底
        avg_task_s = max(60.0, (state["gpu_time_s_total"] / total) + 120.0)
        rework_rate = 0.0
        assignments = self._assignments()
        if assignments:
            reworks = sum(1 for r in assignments.values() if r.get("rework_count", 0) > 0)
            rework_rate = reworks / len(assignments)
        return {
            "task_total": total,
            "active_tasks": active,
            "workers": workers,
            "capacity_slots": workers * 2,          # 每 worker 2 并发槽
            "avg_task_s": avg_task_s,
            "rework_rate": round(rework_rate, 3),
        }

    def _assignments(self) -> dict:
        path = self.root / "team" / "assignments.json"
        if not path.exists():
            return {}
        try:
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def simulate(self, scenario_keys: list[str] | None = None) -> dict:
        base = self._baseline_metrics()
        keys = scenario_keys or list(SCENARIOS.keys())
        results: list[dict] = []
        for key in keys:
            if key not in SCENARIOS:
                continue
            cfg = SCENARIOS[key]
            load = base["task_total"] * cfg["load_factor"]
            capacity = base["capacity_slots"] * cfg["capacity_factor"]
            work_per_task = base["avg_task_s"] * cfg["speed_factor"] * (1 + base["rework_rate"] * cfg["rework_factor"])
            eta_s = (load * work_per_task) / max(1.0, capacity)
            gpu_hours = (load * base["avg_task_s"] * cfg["speed_factor"]) / 3600
            cost = round(gpu_hours * COST_PER_GPU_HOUR, 2)
            bottleneck = self._bottleneck(key, base, cfg)
            results.append({
                "scenario": key,
                "label": cfg["label"],
                "eta_s": int(eta_s),
                "eta_hours": round(eta_s / 3600, 2),
                "cost": cost,
                "bottleneck": bottleneck,
                "assumptions": {
                    "load": int(load),
                    "capacity_slots": round(capacity, 2),
                    "rework_rate": round(base["rework_rate"] * cfg["rework_factor"], 3),
                },
            })
        return {"results": results, "model": "deterministic_queue_model", "auto_control": False}

    def _bottleneck(self, key: str, base: dict, cfg: dict) -> str:
        if key == "gpu_minus_50":
            return "GPU 容量（worker 槽位减半）"
        if key == "speed_down_30":
            return "生成耗时（Wan 推理速度）"
        if key == "rework_up_10":
            return "返工回路（QC 失败放大）"
        if key == "20_episodes":
            return "队列吞吐（任务量放大）"
        return "当前队列"
