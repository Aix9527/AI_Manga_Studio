"""AI Producer Agent service (Phase 14.4, GPT spec).

基于 Executive Producer 能力 + Analytics + Digital Twin + KG：
负责 项目规划 / 资源建议 / 风险解释 / 制作报告；
不负责 自动批准 / 自动调度（所有输出仅建议，人工审批后生效）。
"""

from __future__ import annotations

from backend.command_center.service import CommandCenterService
from backend.digital_twin.service import DigitalTwinService
from backend.knowledge_graph.service import KnowledgeGraphService
from backend.production_intelligence.service import ProductionIntelligenceService


class ProducerAgentService:
    def __init__(self, root: str = "storage"):
        self.cc = CommandCenterService(root=root)
        self.dt = DigitalTwinService(root=root)
        self.kg = KnowledgeGraphService(root=root)
        self.pi = ProductionIntelligenceService(root=root)

    # ------------------------------------------------------------ plan
    def plan(self, project_id: str | None = None) -> dict:
        """项目规划建议：基于当前生产态 / 时间线 / 候选，给出下一步动作建议。"""
        overview = self.cc.overview(project_id=project_id)
        state = overview["production_state"]
        summary = overview["timeline_summary"]
        steps: list[dict] = []

        if state["waiting_human"] > 0:
            steps.append({
                "priority": 1,
                "action": "处理人工审批队列",
                "detail": f"{state['waiting_human']} 个任务等待人工（升级/成片锁定）",
                "evidence": {"waiting_human": state["waiting_human"]},
            })
        if summary["blocked_total"] > 0:
            steps.append({
                "priority": 2,
                "action": "解除依赖阻塞",
                "detail": f"{summary['blocked_total']} 个任务被阻塞（依赖/GPU）",
                "evidence": {"blocked_total": summary["blocked_total"]},
            })
        if state["queue_depth"] > 0:
            steps.append({
                "priority": 3,
                "action": "评估 GPU 容量",
                "detail": f"队列深度 {state['queue_depth']}，建议运行 Queue Simulation 评估容量",
                "evidence": {"queue_depth": state["queue_depth"]},
            })
        if overview["approvals_pending"]["pi_candidates"] > 0:
            steps.append({
                "priority": 4,
                "action": "审批优化候选",
                "detail": f"{overview['approvals_pending']['pi_candidates']} 个优化候选待审批",
                "evidence": {},
            })
        if not steps:
            steps.append({
                "priority": 0,
                "action": "生产正常",
                "detail": "当前无阻塞/等待人工/队列积压，可启动下一集",
                "evidence": {},
            })
        return {
            "project_id": project_id or "",
            "steps": steps,
            "summary": {
                "active_tasks": state["active_tasks"],
                "waiting_human": state["waiting_human"],
                "blocked": summary["blocked_total"],
                "parallel_episodes": summary["parallel_episodes"],
            },
            "auto_approve": False,
            "note": "规划建议仅参考，发布/预算/路由变更需人工审批",
        }

    # ------------------------------------------------------------ resource
    def resource_suggestion(self) -> dict:
        """资源建议：基于 Queue Simulation 对比，给出 GPU/worker 容量建议。"""
        sim = self.dt.simulate(scenario_keys=["baseline", "20_episodes", "gpu_minus_50"])
        by_key = {r["scenario"]: r for r in sim["results"]}
        baseline = by_key["baseline"]
        ep20 = by_key["20_episodes"]
        gpu50 = by_key["gpu_minus_50"]
        suggestions: list[dict] = []
        if ep20["eta_hours"] > baseline["eta_hours"] * 5:
            suggestions.append({
                "kind": "capacity",
                "suggestion": f"20 集并行预计 {ep20['eta_hours']}h（基线 {baseline['eta_hours']}h），"
                              f"建议扩充 GPU/Worker 容量或分批排产",
                "evidence": {"baseline_eta_h": baseline["eta_hours"], "ep20_eta_h": ep20["eta_hours"]},
            })
        if gpu50["eta_hours"] > baseline["eta_hours"] * 1.8:
            suggestions.append({
                "kind": "risk",
                "suggestion": "GPU 减半将显著拉长交付（ETA 放大），建议保留冗余容量",
                "evidence": {"gpu_minus_50_eta_h": gpu50["eta_hours"]},
            })
        return {
            "suggestions": suggestions,
            "auto_schedule": False,
            "note": "资源建议仅参考，GPU 分配/并行度需人工审批（auto_schedule=false）",
        }

    # ------------------------------------------------------------ explain
    def explain_risk(self, candidate_id: str) -> dict:
        """风险解释：RiskCandidate + evidence + 关联 KG 上下文。"""
        candidates = self.dt.risk_candidates()["candidates"]
        target = next((c for c in candidates if c["id"] == candidate_id), None)
        if not target:
            raise KeyError(f"risk candidate not found: {candidate_id}")
        explanation = {
            "schedule": "生产进度压力（队列/等待人工/并行度）",
            "episode": "单集生产异常（阻塞/返工/升级）",
            "quality": "质量风险（QC 失败/返工热点）",
            "asset": "资产风险（反馈事件/候选待审）",
            "budget": "成本风险（估算超预算）",
        }.get(target["risk_type"], "综合风险")
        # 关联 KG 上下文
        related: list[dict] = []
        for key in ("episode", "production", "task_queue"):
            if key in target.get("target_id", ""):
                nodes = self.kg.nodes(q=target.get("target_id", ""), limit=3)
                related = nodes[:3]
                break
        return {
            "candidate": target,
            "explanation": explanation,
            "evidence": target.get("evidence", {}),
            "related_graph_nodes": related,
            "suggestion": target.get("suggestion", ""),
            "auto_fix": False,
            "note": "风险解释仅建议，处理动作需人工决定",
        }

    # ------------------------------------------------------------ report
    def report(self, project_id: str | None = None) -> dict:
        """制作报告：生产态 / 预测 / 风险 / 优化建议 / 规划汇总。"""
        overview = self.cc.overview(project_id=project_id)
        plan = self.plan(project_id=project_id)
        resource = self.resource_suggestion()
        return {
            "project_id": project_id or "",
            "production_state": overview["production_state"],
            "prediction": overview["prediction"],
            "timeline_summary": overview["timeline_summary"],
            "knowledge_graph": overview["knowledge_graph"],
            "risks": overview["risks"],
            "optimization_candidates": overview["intelligence"]["pi_candidates"],
            "plan": plan["steps"],
            "resource_suggestions": resource["suggestions"],
            "approvals_pending": overview["approvals_pending"],
            "governance": overview["governance"],
            "note": "制作报告仅供决策参考，不自动批准/调度",
        }
