"""B2 AnalyticsEngine (Phase 13.5-B, GPT spec).

Cost Intelligence / Cycle Intelligence / Director Intelligence /
Prompt ROI。全部为只读分析，输出证据与指标；决策必须走 B4 人工审批。
"""

from __future__ import annotations

from backend.production_intelligence.model import ProductionEvent
from backend.production_intelligence.warehouse import EventWarehouse

# 成本偏差拆因维度（GPT 规范）
COST_FACTORS = ["retry", "model_switch", "prompt_revision", "identity_failure", "qc_failure"]


class AnalyticsEngine:
    def __init__(self, warehouse: EventWarehouse | None = None):
        self.wh = warehouse or EventWarehouse()

    # ------------------------------------------------------------ Cost
    def cost_intelligence(self, project_id: str | None = None) -> dict:
        episodes = self.wh.episode_metrics(project_id=project_id)
        planned = round(sum(e.cost_planned for e in episodes), 2)
        actual = round(sum(e.cost_actual for e in episodes), 2)
        variance = round(actual - planned, 2)
        # 拆因：从 cost_recorded 事件的 payload.reason 汇总
        factor_cost: dict[str, float] = {f: 0.0 for f in COST_FACTORS}
        unexplained = 0.0
        for ev in self.wh.list_events(event_type="cost_recorded", project_id=project_id):
            p = ev["payload"] or {}
            delta = float(p.get("cost_delta", 0.0))
            reason = p.get("reason", "")
            if reason in factor_cost:
                factor_cost[reason] = round(factor_cost[reason] + delta, 2)
            else:
                unexplained = round(unexplained + delta, 2)
        explained = round(sum(factor_cost.values()), 2)
        explanation_rate = round(explained / variance, 3) if variance else 1.0
        top_factors = sorted(
            [{"factor": k, "cost": v} for k, v in factor_cost.items() if v != 0],
            key=lambda row: row["cost"], reverse=True,
        )
        return {
            "project_id": project_id or "*",
            "planned": planned,
            "actual": actual,
            "variance": variance,
            "factors": top_factors,
            "unexplained": unexplained,
            "explanation_rate": explanation_rate,   # 门禁：≥0.90
        }

    # ------------------------------------------------------------ Cycle
    def cycle_intelligence(self, project_id: str | None = None) -> dict:
        """Lead Time 拆解：waiting / generation / review / approval。"""
        events = self.wh.list_events(project_id=project_id)
        # 按 shot 分组：generation_start → generation_end → qc/review → approval
        timeline: dict[str, list[ProductionEvent]] = {}
        for raw in events:
            ev = ProductionEvent.from_dict(raw)
            key = ev.shot_id or ev.episode_id
            if key:
                timeline.setdefault(key, []).append(ev)
        waiting = generation = review = approval = 0.0
        count = 0
        for _key, evs in timeline.items():
            evs.sort(key=lambda e: e.created_at)
            for i in range(1, len(evs)):
                prev, cur = evs[i - 1], evs[i]
                try:
                    span = max(0.0, _parse_ts(cur.created_at) - _parse_ts(prev.created_at))
                except Exception:  # noqa: BLE001
                    continue
                pair = f"{prev.event_type}>{cur.event_type}"
                if pair == "generation_start>generation_end":
                    generation += span
                elif pair.startswith("generation_end") or pair.startswith("qc_failed"):
                    review += span
                elif pair.endswith(">approval_passed"):
                    approval += span
                else:
                    waiting += span
                count += 1
        lead_time = round(waiting + generation + review + approval, 1)
        def _ratio(part: float) -> float:
            return round(part / lead_time, 3) if lead_time else 0.0
        return {
            "project_id": project_id or "*",
            "lead_time_s": lead_time,
            "segments": {
                "waiting": round(waiting, 1),
                "generation": round(generation, 1),
                "review": round(review, 1),
                "approval": round(approval, 1),
            },
            "ratios": {
                "waiting": _ratio(waiting),
                "generation": _ratio(generation),
                "review": _ratio(review),
                "approval": _ratio(approval),
            },
        }

    # ------------------------------------------------------------ Director
    def director_intelligence(self, project_id: str | None = None) -> list[dict]:
        shots = self.wh.shot_metrics(project_id=project_id)
        groups: dict[str, list] = {}
        for s in shots:
            if s.director:
                groups.setdefault(s.director, []).append(s)
        rows = []
        for director, items in groups.items():
            n = len(items)
            rows.append({
                "director": director,
                "shots": n,
                "success_rate": round(sum(1 for s in items if s.success) / n, 3),
                "avg_quality": round(sum(s.quality for s in items) / n, 3),
                "avg_revision": round(sum(s.revision_count for s in items) / n, 2),
                "total_cost": round(sum(s.cost for s in items), 2),
            })
        rows.sort(key=lambda r: r["success_rate"], reverse=True)
        return rows

    # ------------------------------------------------------------ Prompt ROI
    def prompt_roi(self, project_id: str | None = None) -> list[dict]:
        shots = self.wh.shot_metrics(project_id=project_id)
        groups: dict[str, list] = {}
        for s in shots:
            if s.prompt_version:
                groups.setdefault(s.prompt_version, []).append(s)
        rows = []
        for version, items in groups.items():
            n = len(items)
            rows.append({
                "prompt_version": version,
                "usage": n,
                "success_rate": round(sum(1 for s in items if s.success) / n, 3),
                "avg_quality": round(sum(s.quality for s in items) / n, 3),
                "revision_rate": round(sum(s.revision_count for s in items) / n, 2),
            })
        rows.sort(key=lambda r: r["avg_quality"], reverse=True)
        return rows

    # ------------------------------------------------------------ overview
    def overview(self, project_id: str | None = None) -> dict:
        shots = self.wh.shot_metrics(project_id=project_id)
        episodes = self.wh.episode_metrics(project_id=project_id)
        n = len(shots)
        return {
            "project_id": project_id or "*",
            "episodes": len(episodes),
            "shots": n,
            "success_rate": round(sum(1 for s in shots if s.success) / n, 3) if n else 0.0,
            "avg_quality": round(sum(s.quality for s in shots) / n, 3) if n else 0.0,
            "total_cost": round(sum(s.cost for s in shots), 2),
            "revision_rate": round(sum(s.revision_count for s in shots) / n, 2) if n else 0.0,
        }


def _parse_ts(iso: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001  （Windows 边界/格式异常时跳过该事件）
        return 0.0