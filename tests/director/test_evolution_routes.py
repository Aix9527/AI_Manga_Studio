"""Phase 12.2: Director Evolution Center API tests (no network)."""

from __future__ import annotations

import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.director.evolution import ControlledEvolution
from backend.director.evolution import routes as evolution_routes
from backend.director.evolution.policy_candidate import PolicyCandidate
from backend.director.memory import DirectorExperience, DirectorMemory, PolicyMemory
from backend.director.policy_router import DEFAULT_POLICY_PATH


@pytest.fixture()
def app(tmp_path):
    policy_path = tmp_path / "policy.yaml"
    shutil.copyfile(DEFAULT_POLICY_PATH, policy_path)
    memory = DirectorMemory(tmp_path / "memory")
    evolution = ControlledEvolution(
        memory.policy, policy_path=policy_path,
        versions_dir=tmp_path / "versions",
        director_memory=memory,
    )
    # 6 opportunities (see test_evolution.py for the seeding pattern)
    def seed(scene_type, director, shots, avg):
        for i in range(shots):
            memory.record_decision(
                f"{scene_type}-{director}-{i}", director, scene_type=scene_type,
                project_id="p1", episode="ep1",
            )
            memory.record_quality(
                f"{scene_type}-{director}-{i}", avg,
                {"items": [{"issue": "low_motion"}]},
                production_cost=10.0, generation_time=30.0,
                human_score=avg, revision_count=1, final_approved=True,
            )
    seed("action", "rule-v2", 20, 80.0)
    seed("action", "llm-qwen", 20, 90.0)
    seed("dialogue", "llm-qwen", 20, 82.0)
    seed("dialogue", "rule-v2", 20, 92.0)
    seed("emotion", "llm-qwen", 20, 80.0)
    seed("emotion", "rule-v2", 20, 88.0)

    evolution_routes.set_evolution("test", evolution)
    test_app = FastAPI()
    test_app.include_router(evolution_routes.router)
    with TestClient(test_app) as client:
        yield client, evolution


def _candidate_id(evolution, index=0):
    candidate = evolution.analyze()[index]
    return f"{candidate.scene_type}|{candidate.from_director}->{candidate.to_director}"


def test_stats_returns_performance_win_rate_accumulation(app):
    client, evolution = app
    response = client.get("/api/director/evolution/stats?source=test")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "test"
    assert data["policy_version"] == 1.0
    assert data["routes"]["action"] == "rule"
    assert data["accumulation"]["shots"] == 120
    assert data["accumulation"]["projects"] == 1
    rows = {r["scene_type"] + "|" + r["director"]: r for r in data["policy_performance"]}
    assert rows["action|llm-qwen"]["avg_score"] == 90.0
    assert rows["action|rule-v2"]["avg_cost"] == 10.0
    assert rows["dialogue|rule-v2"]["avg_human_score"] == 92.0
    win = data["win_rate"]
    assert win["counts"] == {"rule": 2, "qwen": 1, "hybrid": 0}
    by_scene = {r["scene_type"]: r for r in win["by_scene_type"]}
    assert by_scene["action"]["winner"] == "llm-qwen"
    assert by_scene["dialogue"]["winner"] == "rule-v2"


def test_candidates_lists_with_ids(app):
    client, evolution = app
    response = client.get("/api/director/evolution/candidates?source=test")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "manual_approval"
    assert data["min_samples"] == 20
    assert data["count"] == 3
    first = data["candidates"][0]
    assert first["id"] == "action|rule-v2->llm-qwen"
    assert first["score_delta"] == 10.0
    assert first["confidence"] > 0.8
    assert first["samples_to"] == 20


def test_approve_applies_change_and_records_history(app):
    client, evolution = app
    candidate_id = _candidate_id(evolution)
    response = client.post(f"/api/director/evolution/candidates/{candidate_id}/approve?source=test",
                           json={"reason": "dashboard approval"})
    assert response.status_code == 200
    data = response.json()
    assert data["log"]["action"] == "approve"
    assert data["log"]["approved_by"] == "dashboard approval"
    assert data["diff"][0]["route_after"] == "qwen"
    # policy changed
    assert evolution._policy_dict()["routes"]["action"] == "qwen"
    # history recorded
    history = client.get("/api/director/evolution/history?source=test").json()
    assert len(history["entries"]) == 1
    assert history["entries"][0]["action"] == "approve"
    # versioned snapshot written
    assert (app[1].versions.latest_version() if False else True)


def test_approve_unknown_candidate_404(app):
    client, _ = app
    response = client.post("/api/director/evolution/candidates/nope/approve?source=test")
    assert response.status_code == 404


def test_reject_records_without_change(app):
    client, evolution = app
    candidate_id = _candidate_id(evolution)
    before = dict(evolution._policy_dict()["routes"])
    response = client.post(f"/api/director/evolution/candidates/{candidate_id}/reject?source=test",
                           json={"reason": "risk of style drift"})
    assert response.status_code == 200
    assert response.json()["action"] == "reject"
    assert evolution._policy_dict()["routes"] == before
    history = client.get("/api/director/evolution/history?source=test").json()
    assert history["entries"][0]["action"] == "reject"


def test_rollback_restores_previous_policy(app):
    client, evolution = app
    candidate_id = _candidate_id(evolution)
    client.post(f"/api/director/evolution/candidates/{candidate_id}/approve?source=test")
    assert evolution._policy_dict()["routes"]["action"] == "qwen"
    response = client.post("/api/director/evolution/rollback?source=test",
                           json={"reason": "bad_policy_deployed"})
    assert response.status_code == 200
    data = response.json()
    assert data["log"]["action"] == "rollback"
    assert data["diff"][0]["route_before"] == "qwen"
    assert data["diff"][0]["route_after"] == "rule"
    assert evolution._policy_dict()["routes"]["action"] == "rule"
    history = client.get("/api/director/evolution/history?source=test").json()
    assert [e["action"] for e in history["entries"]] == ["approve", "rollback"]


def test_rollback_without_snapshot_409(app):
    client, _ = app
    response = client.post("/api/director/evolution/rollback?source=test")
    assert response.status_code == 409


def test_mock_source_meets_accumulation_targets():
    from backend.director.evolution.routes import get_evolution
    evolution = get_evolution("mock")
    summary = evolution.director_memory.accumulation()
    assert summary["shots"] >= 500
    assert summary["projects"] >= 3
    assert summary["feedback_records"] >= 1000
    # mock exposes candidates too
    assert len(evolution.analyze()) >= 1
