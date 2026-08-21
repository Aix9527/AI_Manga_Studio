"""Phase 14.3: Production Command Center tests（三系统融合层）. """

from __future__ import annotations

import json

import pytest

from backend.command_center.service import CommandCenterService


@pytest.fixture()
def service(tmp_path):
    _seed(tmp_path)
    return CommandCenterService(root=str(tmp_path))


def _seed(tmp_path):
    # Runtime / Timeline / Heatmap 数据
    (tmp_path / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "team").mkdir(parents=True, exist_ok=True)
    (tmp_path / "production_intelligence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "feedback").mkdir(parents=True, exist_ok=True)
    (tmp_path / "knowledge_graph").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompt_os").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shot_dna").mkdir(parents=True, exist_ok=True)
    (tmp_path / "digital_twin").mkdir(parents=True, exist_ok=True)

    (tmp_path / "tasks" / "tasks.json").write_text(json.dumps({
        "tasks": {
            "T1": {"task_id": "T1", "project_id": "P1", "status": "running", "worker_id": "W1", "gpu_time_s": 120, "task_type": "video_chain"},
            "T2": {"task_id": "T2", "project_id": "P1", "status": "queued", "worker_id": "W1", "gpu_time_s": 0, "task_type": "video_chain"},
        },
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "team" / "assignments.json").write_text(json.dumps({
        "A1": {"id": "A1", "project_id": "P1", "episode_id": "EP1", "stage": "planning", "role": "Producer",
               "status": "done", "started_at": "2026-08-07T00:00:00", "completed_at": "2026-08-07T00:05:00",
               "attempt": 1, "rework_count": 0, "blocked_reason": ""},
        "A2": {"id": "A2", "project_id": "P1", "episode_id": "EP1", "stage": "generation", "role": "Production",
               "status": "escalated", "started_at": "", "completed_at": "",
               "attempt": 3, "rework_count": 2, "blocked_reason": "GPU 不足"},
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "team" / "teams.json").write_text(json.dumps({
        "TEAM-1": {"id": "TEAM-1", "project_id": "P1", "name": "C 团队", "status": "active"},
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "team" / "reviews.json").write_text("{}", encoding="utf-8")
    (tmp_path / "production_intelligence" / "events.json").write_text(json.dumps({
        "EV1": {"id": "EV1", "event_type": "qc_failed", "project_id": "P1", "episode_id": "EP1"},
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "feedback" / "events.json").write_text("{}", encoding="utf-8")
    (tmp_path / "prompt_os" / "dna.json").write_text("{}", encoding="utf-8")
    (tmp_path / "prompt_os" / "shot_designs.json").write_text("{}", encoding="utf-8")
    (tmp_path / "shot_dna" / "library.json").write_text(json.dumps({"entries": {}}, ensure_ascii=False), encoding="utf-8")
    # KG 摄取一次
    from backend.knowledge_graph.service import KnowledgeGraphService
    KnowledgeGraphService(root=str(tmp_path)).ingest()
    # PI 候选
    from backend.production_intelligence.service import ProductionIntelligenceService
    pi = ProductionIntelligenceService(root=str(tmp_path))
    pi.wh.record_event(event_type="generation_end", project_id="P1", episode_id="EP1", shot_id="S1",
                       payload={"quality": 0.6, "cost": 10, "planned_cost": 8, "cost_delta": 2, "reason": "retry"})
    pi.candidates.propose({"target_type": "episode", "target_id": "EP1", "reason": "retention 低"}, project_id="P1")


def test_command_center_overview(service):
    overview = service.overview()
    assert overview["mode"] == "command_center"
    assert overview["governance"]["auto_control"] is False
    assert overview["governance"]["auto_apply"] is False
    assert overview["note"].startswith("Control Suggestion ≠ Auto Control")
    # 生产态
    assert overview["production_state"]["task_total"] == 2
    assert overview["production_state"]["waiting_human"] == 1
    # 预测
    assert len(overview["prediction"]) == 2
    baseline = next(r for r in overview["prediction"] if r["scenario"] == "baseline")
    ep20 = next(r for r in overview["prediction"] if r["scenario"] == "20_episodes")
    assert ep20["eta_hours"] >= baseline["eta_hours"]
    # KG / PI / 风险
    assert overview["knowledge_graph"]["nodes"] >= 1
    assert overview["intelligence"]["pi_candidates"]
    assert len(overview["risks"]) >= 1
    # 审批入口
    assert overview["approvals_pending"]["waiting_human"] == 1
    assert overview["approvals_pending"]["pi_candidates"] >= 1
    assert overview["audit_coverage"] == 1.0
