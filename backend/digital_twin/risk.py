"""Risk Prediction (Phase 14.2 E, GPT spec).

基于 Runtime + Timeline + KG + Production Intelligence 生成 RiskCandidate
（episode / asset / budget / schedule / quality）。只生成候选，不自动干预。
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from backend.digital_twin.model import RISK_SEVERITIES, RISK_TYPES, RiskCandidate
from backend.digital_twin.runtime import RuntimeMirror, TimelineBuilder


def _new_id() -> str:
    return f"RK-{uuid.uuid4().hex[:10]}"


class RiskPredictor:
    def __init__(self, root: str | Path = "storage"):
        self.root = Path(root)
        self.mirror = RuntimeMirror(root)
        self.timeline = TimelineBuilder(root)
        self._lock = threading.RLock()
        self._candidates: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        path = self.root / "digital_twin" / "risk_candidates.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _save(self) -> None:
        path = self.root / "digital_twin" / "risk_candidates.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._candidates, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _events(self) -> dict:
        path = self.root / "production_intelligence" / "events.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _feedback(self) -> dict:
        path = self.root / "feedback" / "events.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    # ------------------------------------------------------------ predict
    def predict(self, project_id: str | None = None) -> list[dict]:
        state = self.mirror.current_state(project_id=project_id)
        timeline = self.timeline.timeline(project_id=project_id)
        events = self._events()
        feedback = self._feedback()
        generated: list[RiskCandidate] = []

        def add(risk_type: str, target_type: str, target_id: str, severity: str,
                evidence: dict, suggestion: str, pid: str = "") -> None:
            if severity not in RISK_SEVERITIES:
                severity = "medium"
            generated.append(RiskCandidate(
                id=_new_id(), risk_type=risk_type, target_type=target_type,
                target_id=target_id, severity=severity, evidence=evidence,
                suggestion=suggestion, project_id=pid or project_id or "",
            ))

        # Schedule：活跃任务 / 队列 / 等待人工
        active = state["assignment_active"]
        waiting = state["waiting_human"]
        queue = state["queue_depth"]
        if waiting > 0:
            add("schedule", "production", "waiting_human",
                "high" if waiting >= 3 else "medium",
                {"waiting_human": waiting}, "优先处理人工审批队列（escalated 任务）")
        if queue > 0:
            add("schedule", "task_queue", "queued",
                "medium" if queue < 10 else "high",
                {"queue_depth": queue}, "评估 GPU 容量与并行度（可运行 Queue Simulation）")
        if active >= 10:
            add("schedule", "production", "active_assignments",
                "medium", {"active_assignments": active}, "关注多集并行压力")

        # Episode：阻塞 / 返工热点
        if timeline["blocked_total"] > 0:
            add("episode", "production", "blocked",
                "high" if timeline["blocked_total"] >= 3 else "medium",
                {"blocked_total": timeline["blocked_total"]},
                "排查阻塞原因并解除依赖")
        if timeline["rework_total"] >= 3:
            add("episode", "production", "rework",
                "medium", {"rework_total": timeline["rework_total"]},
                "检查返工热点阶段（Heatmap）并定向修复")

        # Quality：QC 失败事件 / 返工
        qc_fail = sum(1 for e in events.values() if e.get("event_type") == "qc_failed")
        if qc_fail > 0:
            add("quality", "production", "qc_failure",
                "high" if qc_fail >= 3 else "medium",
                {"qc_failed_events": qc_fail}, "分析 QC 失败分类并触发定向返工路由")

        # Asset：反馈事件
        if feedback:
            add("asset", "production", "feedback_events",
                "medium", {"feedback_events": len(feedback)},
                "审查 Asset Feedback 候选并审批新版本")

        # Budget：成本估算（gpu_time × 费率 对比计划）
        cost_est = round(state["gpu_time_s_total"] * 0.002, 2)  # 简化估算
        if cost_est > 10:
            add("budget", "production", "cost_estimate",
                "medium", {"cost_estimate": cost_est},
                "运行 Budget Controller 检查预算状态")

        # 持久化（append 候选，同 ID 去重）
        with self._lock:
            for candidate in generated:
                self._candidates[candidate.id] = candidate.to_dict()
            self._save()
        return [c.to_dict() for c in generated]

    # ------------------------------------------------------------ queries
    def list_candidates(self, status: str | None = None) -> list[dict]:
        self._candidates = self._load()      # 读操作前刷新（多实例共享最新数据）
        rows = list(self._candidates.values())
        if status:
            rows = [r for r in rows if r.get("status") == status]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows

    def dismiss(self, candidate_id: str) -> dict:
        self._candidates = self._load()      # 刷新后再操作
        if candidate_id not in self._candidates:
            raise KeyError(f"risk candidate not found: {candidate_id}")
        with self._lock:
            self._candidates[candidate_id]["status"] = "dismissed"
            self._save()
        return self._candidates[candidate_id]
