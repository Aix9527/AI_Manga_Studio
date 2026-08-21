"""Production Command Center service (Phase 14.3, GPT spec).

三系统融合层：Knowledge Graph + Digital Twin + Production Intelligence。
能力：当前生产态 / 未来预测 / 风险 / 优化建议 / 人工审批入口。
Control Suggestion ≠ Auto Control（所有输出仅建议，人工审批后生效）。
"""

from __future__ import annotations

from backend.digital_twin.service import DigitalTwinService
from backend.knowledge_graph.service import KnowledgeGraphService
from backend.production_intelligence.service import ProductionIntelligenceService
from backend.team.service import TeamService


class CommandCenterService:
    def __init__(self, root: str = "storage"):
        self.dt = DigitalTwinService(root=root)
        self.kg = KnowledgeGraphService(root=root)
        self.pi = ProductionIntelligenceService(root=root)
        self.team = TeamService(root=root)

    # ------------------------------------------------------------ overview
    def overview(self, project_id: str | None = None) -> dict:
        state = self.dt.current_state(project_id=project_id)
        timeline = self.dt.timeline(project_id=project_id)
        heatmap = self.dt.heatmap(project_id=project_id)
        sim = self.dt.simulate(scenario_keys=["baseline", "20_episodes"])
        kg_stats = self.kg.stats()
        self.dt.predict(project_id=project_id)          # 刷新风险候选（幂等追加）
        risk_rows = self.dt.risk_candidates()["candidates"]
        pi_stats = self.pi.stats()
        pi_optim = self.pi.list_candidates()          # 已保存待审批候选（人工审批入口）
        team_stats = self.team.stats()

        approvals_pending = {
            "waiting_human": state.get("waiting_human", 0),
            "pi_candidates": pi_stats.get("candidates", {}).get("candidates", 0),
            "risk_candidates": len([r for r in risk_rows if r.get("status") == "proposed"]),
        }
        return {
            "mode": "command_center",
            "governance": {
                "auto_control": False,
                "auto_apply": False,
                "auto_deploy": False,
                "human_approval": True,
            },
            "production_state": {
                "task_total": state.get("task_total", 0),
                "active_tasks": state.get("active_tasks", 0),
                "worker_count": state.get("worker_count", 0),
                "queue_depth": state.get("queue_depth", 0),
                "waiting_human": state.get("waiting_human", 0),
                "assignment_active": state.get("assignment_active", 0),
                "gpu_usage": heatmap.get("gpu", {}).get("usage", 0),
                "worker_idle_rate": state.get("worker_idle_rate", 0),
            },
            "prediction": sim.get("results", []),
            "timeline_summary": {
                "blocked_total": timeline.get("blocked_total", 0),
                "rework_total": timeline.get("rework_total", 0),
                "waiting_human_total": timeline.get("waiting_human_total", 0),
                "parallel_episodes": heatmap.get("production", {}).get("parallel_episodes", 0),
            },
            "knowledge_graph": {
                "nodes": kg_stats.get("nodes", 0),
                "edges": kg_stats.get("edges", 0),
            },
            "intelligence": {
                "pi_candidates": pi_optim,
                "explanation_rate": pi_stats.get("warehouse", {}).get("audit_coverage", 0),
            },
            "risks": risk_rows,
            "approvals_pending": approvals_pending,
            "audit_coverage": team_stats.get("audit_coverage", 1.0),
            "note": "Control Suggestion ≠ Auto Control：所有建议需人工审批后生效",
        }
