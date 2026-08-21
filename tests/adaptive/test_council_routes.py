"""Phase 12.8: Director Council API tests (no network)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.director import council_routes


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(council_routes.router)
    return TestClient(app)


def test_agents_endpoint_lists_five_agents():
    with _client() as client:
        response = client.get("/api/director/council/agents")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 5
        assert data["total_weight"] == 1.0
        names = {a["name"] for a in data["agents"]}
        assert names == {"narrative", "camera", "continuity", "production", "critic"}


def test_run_endpoint_returns_decisions():
    with _client() as client:
        response = client.get("/api/director/council/run?limit=40")
        assert response.status_code == 200
        data = response.json()
        assert len(data["decisions"]) == 40
        assert data["explainable"] == 40


def test_candidates_endpoint_returns_pending_candidates():
    with _client() as client:
        response = client.get("/api/director/council/candidates?limit=200")
        assert response.status_code == 200
        data = response.json()
        assert data["agents"] == ["narrative", "camera", "continuity", "production", "critic"]
        for candidate in data["candidates"]:
            assert candidate["to_director"]
            assert candidate["confidence"] > 0.5
