"""Phase 14.2: Production Digital Twin tests（GPT spec A–E）.

Runtime Mirror / Timeline / Heatmap / Queue Simulation / Risk Prediction。
mode=simulation_and_visibility_only，auto_control=false。
"""

from __future__ import annotations

import json

import pytest

from backend.digital_twin.service import DigitalTwinService


@pytest.fixture()
def service(tmp_path):
    return DigitalTwinService(root=str(tmp_path))


def _seed(tmp_path):
    (tmp_path / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "team").mkdir(parents=True, exist_ok=True)
    (tmp_path / "production_intelligence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "feedback").mkdir(parents=True, exist_ok=True)
    (tmp_path / "digital_twin").mkdir(parents=True, exist_ok=True)

    (tmp_path / "tasks" / "tasks.json").write_text(json.dumps({
        "tasks": {
            "T1": {"task_id": "T1", "project_id": "P1", "status": "running", "worker_id": "W1", "gpu_time_s": 120, "task_type": "video_chain"},
            "T2": {"task_id": "T2", "project_id": "P1", "status": "queued", "worker_id": "W1", "gpu_time_s": 0, "task_type": "video_chain"},
            "T3": {"task_id": "T3", "project_id": "P1", "status": "completed", "worker_id": "W2", "gpu_time_s": 300, "task_type": "video_chain"},
            "T4": {"task_id": "T4", "project_id": "P1", "status": "failed", "worker_id": "", "gpu_time_s": 10, "task_type": "video_chain"},
        },
    }, ensure_ascii=False), encoding="utf-8")

    (tmp_path / "team" / "assignments.json").write_text(json.dumps({
        "A1": {"id": "A1", "project_id": "P1", "episode_id": "EP1", "stage": "planning", "role": "Producer",
               "status": "done", "started_at": "2026-08-07T00:00:00", "completed_at": "2026-08-07T00:05:00",
               "attempt": 1, "rework_count": 0, "blocked_reason": ""},
        "A2": {"id": "A2", "project_id": "P1", "episode_id": "EP1", "stage": "script", "role": "Writer",
               "status": "in_progress", "started_at": "2026-08-07T00:05:00", "completed_at": "",
               "attempt": 2, "rework_count": 1, "blocked_reason": ""},
        "A3": {"id": "A3", "project_id": "P1", "episode_id": "EP2", "stage": "generation", "role": "Production",
               "status": "escalated", "started_at": "", "completed_at": "",
               "attempt": 1, "rework_count": 0, "blocked_reason": "GPU 不足"},
        "A4": {"id": "A4", "project_id": "P1", "episode_id": "EP2", "stage": "sound", "role": "Sound",
               "status": "blocked", "started_at": "", "completed_at": "",
               "attempt": 1, "rework_count": 0, "blocked_reason": "依赖缺失"},
    }, ensure_ascii=False), encoding="utf-8")

    (tmp_path / "production_intelligence" / "events.json").write_text(json.dumps({
        "EV1": {"id": "EV1", "event_type": "qc_failed", "project_id": "P1", "episode_id": "EP1"},
        "EV2": {"id": "EV2", "event_type": "qc_failed", "project_id": "P1", "episode_id": "EP1"},
        "EV3": {"id": "EV3", "event_type": "qc_failed", "project_id": "P1", "episode_id": "EP2"},
    }, ensure_ascii=False), encoding="utf-8")

    (tmp_path / "feedback" / "events.json").write_text(json.dumps({
        "FB1": {"id": "FB1", "target_type": "character", "target_id": "CH1", "kind": "expression_forced"},
    }, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- A
def test_runtime_mirror(service, tmp_path):
    _seed(tmp_path)
    state = service.current_state()
    assert state["task_total"] == 4
    assert state["active_tasks"] == 2          # running + queued
    assert state["worker_count"] == 2
    assert state["queue_depth"] == 1
    assert state["assignment_active"] == 1      # 仅 A2 in_progress（escalated/blocked 不计入 active）
    assert state["waiting_human"] == 1          # A3 escalated
    assert state["gpu_time_s_total"] == 430.0


# ---------------------------------------------------------------- B
def test_timeline(service, tmp_path):
    _seed(tmp_path)
    timeline = service.timeline()
    by_ep = {e["episode_id"]: e for e in timeline["episodes"]}
    assert "EP1" in by_ep and "EP2" in by_ep
    ep1 = by_ep["EP1"]
    assert len(ep1["stages"]) == 2
    planning = [s for s in ep1["stages"] if s["stage"] == "planning"][0]
    assert planning["duration_s"] == 300       # 5 分钟
    assert timeline["blocked_total"] == 2       # A3/A4 均有 blocked_reason
    assert timeline["rework_total"] == 1
    assert timeline["waiting_human_total"] == 1


# ---------------------------------------------------------------- C
def test_heatmap(service, tmp_path):
    _seed(tmp_path)
    hm = service.heatmap()
    assert hm["gpu"]["queue_length"] == 1
    assert hm["gpu"]["active_tasks"] == 2
    assert hm["production"]["parallel_episodes"] == 2
    assert "script" in hm["production"]["retry_hotspots"]
    assert hm["production"]["retry_hotspots"]["script"] == 2   # attempt=2 + rework_count=1


# ---------------------------------------------------------------- D
def test_simulation(service, tmp_path):
    _seed(tmp_path)
    result = service.simulate()
    keys = {r["scenario"] for r in result["results"]}
    assert keys == {"baseline", "20_episodes", "gpu_minus_50", "speed_down_30", "rework_up_10"}
    by_key = {r["scenario"]: r for r in result["results"]}
    assert by_key["gpu_minus_50"]["eta_hours"] > by_key["baseline"]["eta_hours"]
    assert by_key["20_episodes"]["eta_hours"] > by_key["baseline"]["eta_hours"]
    assert by_key["gpu_minus_50"]["bottleneck"] == "GPU 容量（worker 槽位减半）"
    assert result["auto_control"] is False
    # 指定场景
    sub = service.simulate(scenario_keys=["baseline", "rework_up_10"])
    assert len(sub["results"]) == 2


# ---------------------------------------------------------------- E
def test_risk_prediction(service, tmp_path):
    _seed(tmp_path)
    result = service.predict()
    assert result["auto_control"] is False
    assert result["count"] >= 3
    types = {c["risk_type"] for c in result["candidates"]}
    assert "schedule" in types           # waiting_human=1
    assert "quality" in types            # qc_failed=3
    assert "episode" in types            # blocked_total=1 / rework
    # 持久化
    listed = service.risk_candidates()
    assert listed["candidates"]
    # dismiss
    first = listed["candidates"][0]
    dismissed = service.dismiss_risk(first["id"])
    assert dismissed["status"] == "dismissed"
    assert service.risk_candidates(status="dismissed")["candidates"]


# ---------------------------------------------------------------- overview
def test_overview_and_mode(service, tmp_path):
    _seed(tmp_path)
    overview = service.overview()
    assert overview["mode"] == "simulation_and_visibility_only"
    assert overview["auto_control"] is False
    assert overview["state"]["task_total"] == 4
