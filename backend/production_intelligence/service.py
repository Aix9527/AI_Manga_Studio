"""Production Intelligence service (Phase 13.5-B, GPT spec).

B1 EventWarehouse + MetricsEngine → B2 AnalyticsEngine → B3 IntelligenceCenter
→ B4 CandidateEngine（Analytics → Candidate → Human Review → Apply → Audit）。
Analytics 不是决策者：候选必须人工审批，应用只记录审计结果，不自动修改
生产资产（auto_learning=false / auto_apply=false / 自动修改 0）。
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from backend.production_intelligence.analytics import AnalyticsEngine
from backend.production_intelligence.center import IntelligenceCenter
from backend.production_intelligence.model import AnalyticsCandidate, CANDIDATE_STATUSES, TARGET_TYPES
from backend.production_intelligence.warehouse import EventWarehouse


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class CandidateEngine:
    """B4：优化建议 → 候选 → 人工审批 → 应用（审计记录，不自动改资产）。"""

    def __init__(self, root: str | Path = "storage/production_intelligence"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, dict] = self._load("candidates.json")

    def _load(self, name: str) -> dict[str, dict]:
        path = self.root / name
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save(self, name: str, data: dict[str, dict]) -> None:
        path = self.root / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def propose(self, suggestion: dict, *, project_id: str = "") -> dict:
        target_type = suggestion.get("target_type", "episode")
        if target_type not in TARGET_TYPES:
            raise ValueError(f"invalid target type: {target_type}")
        candidate = AnalyticsCandidate(
            id=_new_id("AC"),
            target_type=target_type,
            target_id=suggestion.get("target_id", ""),
            project_id=project_id or suggestion.get("project_id", ""),
            suggested_changes=suggestion.get("suggested_changes", {}),
            evidence=suggestion.get("evidence", {}),
            reason=suggestion.get("reason", ""),
            status="proposed",
        )
        with self._lock:
            self._data[candidate.id] = candidate.to_dict()
            self._save("candidates.json", self._data)
        return candidate.to_dict()

    def propose_many(self, suggestions: list[dict], *, project_id: str = "") -> list[dict]:
        return [self.propose(s, project_id=project_id) for s in suggestions]

    def list(self, status: str | None = None) -> list[dict]:
        rows = list(self._data.values())
        if status:
            rows = [r for r in rows if r.get("status") == status]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows

    def review(self, candidate_id: str, decision: str, reviewer: str = "human") -> dict:
        if decision not in ("approved", "rejected"):
            raise ValueError(f"decision 必须是 approved 或 rejected，收到 {decision}")
        raw = self._data.get(candidate_id)
        if not raw:
            raise KeyError(f"candidate not found: {candidate_id}")
        if raw["status"] != "proposed":
            raise ValueError(f"只有 proposed 候选可以审批，当前 {raw['status']}")
        raw["status"] = decision
        raw["reviewer"] = reviewer
        raw["decided_at"] = _now()
        with self._lock:
            self._data[candidate_id] = raw
            self._save("candidates.json", self._data)
        return dict(raw)

    def apply(self, candidate_id: str) -> dict:
        """应用 = 生成审计记录 + 标记 applied；绝不自动修改生产资产。"""
        raw = self._data.get(candidate_id)
        if not raw:
            raise KeyError(f"candidate not found: {candidate_id}")
        if raw["status"] != "approved":
            raise ValueError(f"只有 approved 候选可以应用，当前 {raw['status']}")
        if raw.get("applied_at"):
            raise ValueError("该候选已应用，禁止重复应用")
        raw["status"] = "applied"
        raw["applied_at"] = _now()
        with self._lock:
            self._data[candidate_id] = raw
            self._save("candidates.json", self._data)
        return dict(raw)

    def stats(self) -> dict:
        statuses: dict[str, int] = {}
        for raw in self._data.values():
            statuses[raw.get("status", "proposed")] = statuses.get(raw.get("status", "proposed"), 0) + 1
        return {
            "candidates": len(self._data),
            "by_status": statuses,
            "auto_learning": False,
            "auto_apply": False,
        }


class ProductionIntelligenceService:
    """总服务：B1+B2+B3+B4 组装。"""

    def __init__(
        self,
        root: str | Path = "storage/production_intelligence",
        *,
        warehouse: EventWarehouse | None = None,
        analytics: AnalyticsEngine | None = None,
        center: IntelligenceCenter | None = None,
        candidates: CandidateEngine | None = None,
    ):
        self.wh = warehouse or EventWarehouse(root)
        self.analytics = analytics or AnalyticsEngine(self.wh)
        self.center = center or IntelligenceCenter(self.analytics)
        self.candidates = candidates or CandidateEngine(root)

    # ---- B1
    def record_event(self, **kwargs) -> dict:
        return self.wh.record_event(**kwargs)

    def list_events(self, **kwargs) -> list[dict]:
        return self.wh.list_events(**kwargs)

    def warehouse_stats(self) -> dict:
        return self.wh.stats()

    # ---- B2
    def cost_intelligence(self, project_id: str | None = None) -> dict:
        return self.analytics.cost_intelligence(project_id=project_id)

    def cycle_intelligence(self, project_id: str | None = None) -> dict:
        return self.analytics.cycle_intelligence(project_id=project_id)

    def director_intelligence(self, project_id: str | None = None) -> list[dict]:
        return self.analytics.director_intelligence(project_id=project_id)

    def prompt_roi(self, project_id: str | None = None) -> list[dict]:
        return self.analytics.prompt_roi(project_id=project_id)

    # ---- B3
    def overview(self, project_id: str | None = None) -> dict:
        return self.center.overview(project_id=project_id)

    def episode_roi(self, project_id: str | None = None) -> list[dict]:
        return self.center.episode_roi(project_id=project_id)

    def risk_radar(self, project_id: str | None = None) -> list[dict]:
        return self.center.risk_radar(project_id=project_id)

    def optimization_candidates(self, project_id: str | None = None) -> list[dict]:
        return self.center.optimization_candidates(project_id=project_id)

    # ---- B4
    def propose_candidates(self, project_id: str | None = None) -> list[dict]:
        suggestions = self.center.optimization_candidates(project_id=project_id)
        return self.candidates.propose_many(suggestions, project_id=project_id or "")

    def list_candidates(self, status: str | None = None) -> list[dict]:
        return self.candidates.list(status=status)

    def review_candidate(self, candidate_id: str, decision: str, reviewer: str = "human") -> dict:
        return self.candidates.review(candidate_id, decision, reviewer)

    def apply_candidate(self, candidate_id: str) -> dict:
        return self.candidates.apply(candidate_id)

    def candidate_stats(self) -> dict:
        return self.candidates.stats()

    # ---- overall
    def stats(self) -> dict:
        return {
            "warehouse": self.wh.stats(),
            "candidates": self.candidates.stats(),
            "governance": {
                "auto_learning": False,
                "auto_apply": False,
                "auto_deploy": False,
                "human_approval": True,
                "rollback": True,
                "audit": True,
            },
        }