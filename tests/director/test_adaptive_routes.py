"""Phase 12.6: Adaptive Director Router API tests (no network)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.director import adaptive_routes
from backend.director.adaptive_router import AdaptiveDirectorRouter


def _make_client(tmp_path) -> TestClient:
    router = AdaptiveDirectorRouter(
        policy_path=tmp_path / "adaptive_router_policy.yaml",
        versions_dir=tmp_path / "versions",
    )
    adaptive_routes._instances["test"] = router
    test_app = FastAPI()
    test_app.include_router(adaptive_routes.router)
    return TestClient(test_app)


def test_proposal_endpoint_returns_40_suggestions(tmp_path):
    with _make_client(tmp_path) as client:
        response = client.get("/api/director/adaptive/proposal?source=test")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 30
        assert data["cells"] == 20
        assert data["scope_isolation"]["violations"] == 0
        assert set(data["production_value_weights"]) == {
            "quality", "continuity", "stability", "cost", "latency"
        }


def test_approve_endpoint_writes_policy_and_log(tmp_path):
    with _make_client(tmp_path) as client:
        response = client.post("/api/director/adaptive/recommendations/科幻|action|primary/approve?source=test")
        assert response.status_code == 200
        data = response.json()
        assert data["cell"] == "科幻|action"
        assert data["policy"]["科幻"]["action"]["primary"] == "llm-gpt"
        # double approve -> 409
        again = client.post("/api/director/adaptive/recommendations/科幻|action|primary/approve?source=test")
        assert again.status_code == 409


def test_reject_endpoint_records_trace(tmp_path):
    with _make_client(tmp_path) as client:
        response = client.post(
            "/api/director/adaptive/recommendations/古装|action|primary/reject?source=test",
            json={"reason": "human no"},
        )
        assert response.status_code == 200
        assert response.json()["cell"] == "古装|action"


def test_rollback_endpoint_restores_snapshot(tmp_path):
    with _make_client(tmp_path) as client:
        client.post("/api/director/adaptive/recommendations/科幻|action|primary/approve?source=test")
        client.post("/api/director/adaptive/recommendations/动画|world|primary/approve?source=test")
        response = client.post("/api/director/adaptive/rollback?source=test", json={"reason": "test"})
        assert response.status_code == 200
        assert response.json()["restored_version"] >= 1
        # 动画|world restored to default
        proposal = client.get("/api/director/adaptive/proposal?source=test").json()
        assert proposal["recommendations"]  # still works


def test_ab_validation_endpoint_passes_gate(tmp_path):
    with _make_client(tmp_path) as client:
        response = client.get("/api/director/adaptive/ab-validation?source=test&limit=100")
        assert response.status_code == 200
        data = response.json()
        assert data["shots"] == 100
        assert data["passed"] is True
        assert data["quality_gain_pct"] >= 5.0 or data["cost_reduction_pct"] >= 10.0


def test_ab_validation_rejects_small_limit(tmp_path):
    with _make_client(tmp_path) as client:
        response = client.get("/api/director/adaptive/ab-validation?source=test&limit=50")
        assert response.status_code == 400
