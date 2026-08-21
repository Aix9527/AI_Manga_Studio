"""Phase 15.1：归墟第二部 100 集工业生产 Pilot runner。

复用 Team Collaboration（900 assignments）/ Production Intelligence（事件）/
KG / Digital Twin / Producer Agent 全链路，做首次真实规模压力验证。
无真实 GPU 时以确定性成本/质量模拟灌入（真实镜头生成留待 GPU 就绪）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from backend.command_center.service import CommandCenterService
from backend.digital_twin.service import DigitalTwinService
from backend.knowledge_graph.service import KnowledgeGraphService
from backend.production_pilot.parser import build_episode_plan
from backend.production_intelligence.service import ProductionIntelligenceService
from backend.producer_agent.service import ProducerAgentService
from backend.team.model import STAGE_REVIEW_OWNER
from backend.team.service import TeamService

STAGES = [
    ("planning", "Producer"), ("script", "Writer"), ("storyboard", "Director"),
    ("assets", "Director"), ("generation", "Production"), ("qc", "Reviewer"),
    ("editing", "Editor"), ("sound", "Sound"), ("final", "Producer"),
]


class PilotRunner:
    def __init__(self, root: str | Path = "storage", script_path: str | None = None):
        self.root = Path(root)
        self.script_path = script_path
        self.team = TeamService(self.root / "team")
        self.pi = ProductionIntelligenceService(self.root / "production_intelligence")
        self.kg = KnowledgeGraphService(root=str(self.root))
        self.dt = DigitalTwinService(root=str(self.root))
        self.cc = CommandCenterService(root=str(self.root))
        self.producer = ProducerAgentService(root=str(self.root))

    # ------------------------------------------------------------ plan
    def plan(self) -> dict:
        return build_episode_plan(self.script_path)

    def init(self) -> dict:
        plan = self.plan()
        project_id = plan["project_id"]
        role_bindings = {
            "Producer": ["admin"], "Planner": ["admin"], "Writer": ["writer-agent"],
            "Director": ["director-agent"], "Editor": ["editor-agent"], "Sound": ["sound-agent"],
            "Production": ["worker-1", "worker-2"], "Reviewer": ["qc-agent"], "Analyst": ["analyst-agent"],
        }
        self.team.create_team(project_id=project_id, name="归墟第二部制作团队",
                              season_id="S1", role_bindings=role_bindings,
                              actor="admin", reason="15.1 Pilot 初始化")
        return plan

    # ------------------------------------------------------------ orchestrate
    def run_episodes(self, limit: int | None = None, *, progress: bool = False) -> dict:
        """100 集 × 9 阶段编排（Team Collaboration）；limit 用于测试/增量。"""
        plan = self.init()
        episodes = plan["episodes"]
        if limit:
            episodes = episodes[:limit]
        started = time.time()
        rows: list[dict] = []
        for ep in episodes:
            ep_rows = []
            for stage_idx, (stage, role) in enumerate(STAGES):
                deps = [ep_rows[-1]["id"]] if ep_rows else []
                a = self.team.assign(
                    project_id=plan["project_id"], episode_id=ep["id"], stage=stage, role=role,
                    assignee_type="agent", assignee_id=f"{ep['id']}-{role}",
                    task_id=f"TASK-{ep['id']}-{stage_idx}", dependencies=deps,
                    actor="orchestrator", reason=f"分派{stage}",
                )
                ep_rows.append(a)
            for row in ep_rows:
                self._advance_ok(row, stage_idx_for(row))
            rows.extend(ep_rows)
            if progress:
                print(f"  pilot: {ep['id']} done ({len(rows)}/{len(episodes) * 9})")
        elapsed = time.time() - started
        stats = self.team.stats()
        return {
            "episodes_planned": len(episodes),
            "assignments_total": len(rows),
            "elapsed_s": round(elapsed, 2),
            "assignments_done": stats["by_status"].get("done", 0),
            "audit_coverage": stats["audit_coverage"],
            "illegal_transitions": stats["illegal_transitions"],
        }

    def _advance_ok(self, row: dict, stage: str) -> None:
        self.team.start(row["id"], actor=row["assignee_id"], reason="开工")
        self.team.review(
            assignment_id=row["id"],
            reviewer_role=STAGE_REVIEW_OWNER.get(stage, "Reviewer"),
            reviewer_id="rv", verdict="approve", evidence={"pilot_ok": True},
            actor="rv", reason="评审通过",
            approval_id="AP-FINAL" if stage == "final" else "",
        )
        self.team.complete(row["id"], actor="rv", reason="完成",
                           approval_id="AP-FINAL" if stage == "final" else "")

    # ------------------------------------------------------------ events
    def seed_events(self, limit: int | None = None) -> dict:
        """灌入生产事件（generation_end / qc / cost）→ Production Intelligence。"""
        plan = self.plan()
        episodes = plan["episodes"]
        if limit:
            episodes = episodes[:limit]
        project_id = plan["project_id"]
        count = 0
        for ep in episodes:
            for shot_no in range(1, 6):   # 每集 5 镜
                shot = f"{ep['id']}-S{shot_no}"
                quality = 0.82 if shot_no % 7 else 0.58        # 少量 QC 失败
                cost = 6.0 + (shot_no % 3)
                self.pi.record_event(event_type="generation_start", project_id=project_id,
                                     episode_id=ep["id"], shot_id=shot, audit_id=f"AUD-{shot}",
                                     payload={"director": "导演A", "prompt_version": "pv1",
                                              "shot_dna_id": f"dna{shot_no % 5 + 1}",
                                              "cost_planned": 6.0})
                self.pi.record_event(event_type="generation_end", project_id=project_id,
                                     episode_id=ep["id"], shot_id=shot, audit_id=f"AUD-{shot}",
                                     payload={"quality": quality, "retention": 0.62,
                                              "cost_actual": cost, "cost_delta": round(cost - 6.0, 2),
                                              "reason": "retry" if quality < 0.6 else ""})
                if quality < 0.6:
                    self.pi.record_event(event_type="qc_failed", project_id=project_id,
                                         episode_id=ep["id"], shot_id=shot, audit_id=f"AUD-{shot}",
                                         payload={"qc_score": quality})
                count += 2
        return {"project_id": project_id, "events_recorded": count}

    # ------------------------------------------------------------ report
    def report(self) -> dict:
        plan = self.plan()
        project_id = plan["project_id"]
        kg_stats = self.kg.stats()
        pi_stats = self.pi.stats()
        team_stats = self.team.stats()
        sim = self.dt.simulate(scenario_keys=["baseline", "20_episodes"])
        pred = self.dt.predict(project_id=project_id)
        timeline = self.dt.timeline(project_id=project_id)
        return {
            "project_id": project_id,
            "title": plan["title"],
            "total_episodes": plan["total_episodes"],
            "orchestration": {
                "assignments": team_stats["assignments"],
                "done": team_stats["by_status"].get("done", 0),
                "audit_coverage": team_stats["audit_coverage"],
                "illegal_transitions": team_stats["illegal_transitions"],
                "new_queue_count": team_stats["new_queue_count"],
            },
            "knowledge_graph": {
                "nodes": kg_stats["nodes"],
                "edges": kg_stats["edges"],
                "by_type": kg_stats["by_type"],
            },
            "analytics": {
                "events": pi_stats["warehouse"]["events"],
                "shot_metrics": pi_stats["warehouse"]["shot_metrics"],
                "audit_coverage": pi_stats["warehouse"]["audit_coverage"],
            },
            "digital_twin": {
                "prediction": sim["results"],
                "risk_candidates": pred["count"],
                "timeline": {
                    "blocked": timeline["blocked_total"],
                    "rework": timeline["rework_total"],
                    "waiting_human": timeline["waiting_human_total"],
                },
            },
            "validation_targets": {
                "kg_growth": "PASS" if kg_stats["nodes"] >= 100 else "PENDING",
                "dt_prediction": "PASS" if len(sim["results"]) >= 2 else "PENDING",
                "analytics_roi": "PASS" if pi_stats["warehouse"]["episode_metrics"] >= 1 else "PENDING",
                "audit_coverage": "PASS" if team_stats["audit_coverage"] == 1.0 else "PENDING",
            },
        }


def stage_idx_for(row: dict) -> str:
    return row.get("stage", "")
