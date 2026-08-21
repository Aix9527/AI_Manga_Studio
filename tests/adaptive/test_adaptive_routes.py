"""Phase 12.7-A: Adaptive Dispatcher API tests (no network)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.orchestration import adaptive_routes
from backend.orchestration.adaptive_dispatcher import AdaptiveDispatcher


def _client() -> TestClient:
    adaptive_routes._dispatch = AdaptiveDispatcher()
    app = FastAPI()
    app.include_router(adaptive_routes.router)
    return TestClient(app)


def test_dispatch_endpoint():
    with _client() as client:
        response = client.post("/api/orchestration/adaptive/dispatch", json={
            "project": "归墟觉醒·天倾", "genre": "科幻", "scene_type": "world",
            "shot_type": "wide", "style": "cold_blue", "shot_id": "s001",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["primary_director"] == "llm-gpt"
        assert data["fallback"] == "rule-v2"
        assert "rule-v2" in data["provider_chain"]


def test_ab_endpoint():
    with _client() as client:
        response = client.get("/api/orchestration/adaptive/ab?limit=100")
        assert response.status_code == 200
        data = response.json()
        assert data["shots"] == 100
        assert data["passed"] is True


def test_ab_endpoint_rejects_small_limit():
    with _client() as client:
        response = client.get("/api/orchestration/adaptive/ab?limit=50")
        assert response.status_code == 400


def test_failure_endpoint():
    with _client() as client:
        response = client.get("/api/orchestration/adaptive/failure?unavailable=llm-gpt")
        assert response.status_code == 200
        data = response.json()
        assert data["degraded"] is True
        assert data["resolved"] != "llm-gpt"


def test_scope_endpoint():
    with _client() as client:
        response = client.get("/api/orchestration/adaptive/scope")
        assert response.status_code == 200
        data = response.json()
        assert data["scope_key_isolated"] is True
