"""B3 IntelligenceCenter (Phase 13.5-B, GPT spec).

Production Overview / Episode ROI / Risk Radar / Optimization Candidates。
只读分析视图；优化建议只是建议，落地必须走 B4 人工审批。
"""

from __future__ import annotations

from backend.production_intelligence.analytics import AnalyticsEngine
from backend.production_intelligence.model import EpisodeMetric


class IntelligenceCenter:
    def __init__(self, analytics: AnalyticsEngine | None = None):
        self.analytics = analytics or AnalyticsEngine()

    # ------------------------------------------------------------ overview
    def overview(self, project_id: str | None = None) -> dict:
        base = self.analytics.overview(project_id=project_id)
        cost = self.analytics.cost_intelligence(project_id=project_id)
        cycle = self.analytics.cycle_intelligence(project_id=project_id)
        return {**base, "cost": cost, "cycle": cycle}

    # ------------------------------------------------------------ Episode ROI
    def episode_roi(self, project_id: str | None = None) -> list[dict]:
        rows: list[dict] = []
        for em in self.analytics.wh.episode_metrics(project_id=project_id):
            cost = em.cost_actual or em.cost_planned or 1.0
            roi = round(em.avg_qc / cost, 4) if cost else 0.0
            rows.append({
                "episode_id": em.episode_id,
                "project_id": em.project_id,
                "retention": em.retention,
                "hook_score": em.hook_score,
                "cliffhanger": em.cliffhanger,
                "avg_qc": em.avg_qc,
                "failure_rate": em.failure_rate,
                "cost_actual": em.cost_actual,
                "cost_planned": em.cost_planned,
                "roi": roi,                      # 质量分 / 成本
                "lead_time_s": em.lead_time_s,
            })
        rows.sort(key=lambda r: r["roi"], reverse=True)
        return rows

    # ------------------------------------------------------------ Risk Radar
    def risk_radar(self, project_id: str | None = None, *, qc_threshold: float = 0.25,
                   cost_overrun_ratio: float = 1.1, lead_time_max: float = 3600.0,
                   revision_max: float = 1.5) -> list[dict]:
        risks: list[dict] = []
        for em in self.analytics.wh.episode_metrics(project_id=project_id):
            if em.failure_rate > qc_threshold:
                risks.append(_risk("qc_failure_rate", em.episode_id, em.failure_rate,
                                   f"失败率 {em.failure_rate:.0%} 超过阈值 {qc_threshold:.0%}"))
            if em.cost_actual > em.cost_planned * cost_overrun_ratio and em.cost_planned > 0:
                ratio = round(em.cost_actual / em.cost_planned, 2)
                risks.append(_risk("cost_overrun", em.episode_id, ratio,
                                   f"实际成本为计划的 {ratio:.2f} 倍"))
            if em.lead_time_s > lead_time_max:
                risks.append(_risk("long_lead_time", em.episode_id, em.lead_time_s,
                                   f"单集 Lead Time {em.lead_time_s:.0f}s 超过上限"))
        for sm in self.analytics.wh.shot_metrics(project_id=project_id):
            if sm.revision_count > revision_max:
                risks.append(_risk("high_revision", sm.shot_id, sm.revision_count,
                                   f"镜头 {sm.shot_id} 修订 {sm.revision_count} 次"))
        risks.sort(key=lambda r: r["severity"], reverse=True)
        return risks

    # ------------------------------------------------------------ Candidates
    def optimization_candidates(self, project_id: str | None = None) -> list[dict]:
        """从分析结论生成优化建议（规则驱动，不落地）。"""
        suggestions: list[dict] = []
        cost = self.analytics.cost_intelligence(project_id=project_id)
        if cost["variance"] > 0 and cost["factors"]:
            top = cost["factors"][0]
            suggestions.append({
                "target_type": "resource",
                "target_id": project_id or "*",
                "reason": f"成本超支 {cost['variance']:.2f}，首要因素 {top['factor']}（{top['cost']:.2f}）",
                "suggested_changes": {"focus": top["factor"], "action": "review_generation_settings"},
                "evidence": {"variance": cost["variance"], "explanation_rate": cost["explanation_rate"]},
            })
        for row in self.analytics.prompt_roi(project_id=project_id):
            if row["revision_rate"] >= 1.0 or row["success_rate"] < 0.6:
                suggestions.append({
                    "target_type": "prompt_version",
                    "target_id": row["prompt_version"],
                    "reason": f"Prompt {row['prompt_version']} 修订率 {row['revision_rate']} / 成功率 {row['success_rate']:.0%}",
                    "suggested_changes": {"action": "prompt_revision", "target_version": row["prompt_version"]},
                    "evidence": row,
                })
        for em in self.analytics.wh.episode_metrics(project_id=project_id):
            if em.hook_score < 0.4:
                suggestions.append({
                    "target_type": "episode",
                    "target_id": em.episode_id,
                    "reason": f"集 {em.episode_id} 钩子分 {em.hook_score:.2f} 偏低",
                    "suggested_changes": {"action": "strengthen_hook", "field": "hook_score"},
                    "evidence": {"hook_score": em.hook_score, "retention": em.retention},
                })
        return suggestions[:20]


def _risk(risk_type: str, target_id: str, value: float, message: str) -> dict:
    severity = min(1.0, max(0.1, value / 2.0)) if risk_type != "cost_overrun" else min(1.0, value / 2.0)
    return {
        "risk_type": risk_type,
        "target_id": target_id,
        "value": round(value, 3),
        "severity": round(severity, 3),
        "message": message,
    }